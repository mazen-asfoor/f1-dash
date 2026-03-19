import pandas as pd
import streamlit as st
import fastf1
from utils import fetch_f1_data
import fastf1.plotting as fastplt
import plotly.express as px
import numpy as np


fastf1.Cache.enable_cache('cache')

st.set_page_config(page_title="Plotting Demo", page_icon="📈", layout="wide")

st.markdown("# Pace Analysis")
# st.sidebar.header("Plotting Demo")



session = fetch_f1_data(st.session_state.selected_year, st.session_state.gp, st.session_state.event[0])
# st.dataframe(session.results)


# data setup:




# Graphs

# 1) pace boxplot of all drivers:

teams = session.results[['Abbreviation', 'TeamName']].set_index('Abbreviation').to_dict()['TeamName']

laps = session.laps.pick_accurate()[['Driver', 'Stint', 'Compound', 'DriverNumber', 'SpeedST', 'LapTime', 'TyreLife']]

laps['LapTime'] = laps['LapTime'].dt.total_seconds()
laps['Team'] = laps.Driver.map(teams)

average_pace = laps.groupby('Driver')['LapTime'].mean().sort_values()

team_colors = {}
driver_team = {}
for d in laps.Driver.unique():
    team = laps[laps.Driver == d]['Team'].iloc[0]
    driver_team[d] = team
    team_colors[team] = fastplt.get_team_color(team, session)

laps['color'] = laps.Team.map(team_colors)


keys = {}
for driv in average_pace.index.to_list():
    keys[driv] = average_pace.index.to_list().index(driv)
laps = laps.sort_values(by='Driver', key=lambda x: x.map(keys)).reset_index(drop=True)

driver_color_map = dict(zip(laps['Driver'], laps['color']))



def create_ticks(df=laps):
    ticks = []

    for d in df.Driver.unique():
        avg = df[df.Driver == d]['LapTime'].mean()
        bst_avg = average_pace.iloc[0]
        diff =  f"+{avg-bst_avg:.2f}"
    
        avg = str(round(avg, 2))
        # diff = f'+{str(round(diff, 2))}'
        
        stnt = ''
        compounds = df[df.Driver==d][['Stint', 'Compound']].value_counts().sort_index().index
        for c in range(len(compounds)):
            stnt = stnt + compounds[c][1][0]+'-'
            if len(stnt) <=3:
                pass
            elif (len(stnt) > 3) & (len(stnt.replace('-', '')) % 2 == 0):
                stnt = stnt[:-2] + compounds[c][1][0]+'<br>'
                
        # print(stnt)
        if stnt[-1] == '-':
            stnt = stnt[:-1]
        else:
            stnt = stnt[:-4]

        b = '<br>'
        tick = d+b+avg+b+diff+b+stnt

        ticks.append(tick)
    return ticks
    



def pace_box(tcks = average_pace.index):
# 1. Create the color mapping dictionary {Driver: HexCode}

    # 2. Generate the plot
    fig = px.box(
        laps, 
        x="Driver", 
        y="LapTime", 
        color="Driver",
        color_discrete_map=driver_color_map, 
        hover_data=laps.columns,
        title='Pace distribution'
    )
    fig.update_traces(boxmean=True)
    fig.update_xaxes(title_text = '',
                    tickmode = 'array',
                    tickvals= list(range(len(laps.Driver.unique()))),
                    ticktext = tcks,
                    tickangle=0)
    fig.update_yaxes(title_text = 'Lap Time (seconds)')

    fig.update_layout(
    margin=dict(
        l=10,  # Left margin
        r=10,  # Right margin
        t=40,  # Top margin (leave a bit for the title if needed)
        b=10   # Bottom margin
    ),
    autosize=True
)

    return fig


st.plotly_chart(pace_box(tcks=create_ticks()))


consistency = laps.groupby('Driver')['LapTime'].std().sort_values(ascending=False)
def plotly_barh(df, title, xlbl, ylbl, xlim, color_map):
    fig = px.bar(x=df.values, y=df.index, color=df.index, color_discrete_map=color_map, title=title)
    fig.update_traces(width=0.8)
    fig.update_layout(
        xaxis=dict(
            title=xlbl,
            tickformat=".2f", # Format as 2 decimal places
            showgrid=True,
            range = xlim
        ),
        yaxis=dict(
            title=ylbl,
            tickfont=dict(size=12)
        )
    )
    fig.update_layout(legend_traceorder="reversed")

    return fig
max_speeds = laps.groupby('Driver')['SpeedST'].max().sort_values(ascending=True)




cols = st.columns(2)
with cols[0]:
    st.plotly_chart(plotly_barh(consistency, 
                                'Driver Consistency', 
                                'Standard Deviation (\u00B1 time(s))',
                                  'Drivers', [0, consistency.max()+0.2],
                                   color_map=driver_color_map))
with cols[1]:
    st.plotly_chart(plotly_barh(max_speeds, 
                                'Maximum Speed on Main Straight', 
                                'Speed (km/h)',
                                  'Drivers', [max_speeds.min()-10, max_speeds.max()+10],
                                   color_map=driver_color_map))


fastest20 = session.laps.iloc[np.r_[session.laps.LapTime.nsmallest(20).index]][['Driver', 'LapTime', 'LapNumber', 'Stint', 'Compound', 'TyreLife']].reset_index(drop=True)
fastest20['Team'] = fastest20.Driver.map(driver_team)
fastest20 = fastest20[['Driver', 'Team', 'LapTime', 'LapNumber', 'Stint', 'Compound', 'TyreLife']]
fastest20['LapTime'] = fastest20['LapTime'].apply(lambda x: str(x)[10:])
fastest20['Compound'] = fastest20['Compound'].apply(lambda x: x[0])
fastest20['Stint'] = fastest20['Stint'].apply(lambda x: int(x))

def apply_team_colors(column):
    # Map the team name to the hex code, default to empty string if not found
        return [f'background-color: {team_colors.get(t, "")}' for t in column]

cols = st.columns(2)
with cols[0]:
    st.dataframe(fastest20.style.apply(apply_team_colors, subset=['Team']))
with cols[1]:
    df = pd.DataFrame({'Value': [-10, 20, -5, 50]})
    # Highlights the maximum value in each column
    st.dataframe(df)




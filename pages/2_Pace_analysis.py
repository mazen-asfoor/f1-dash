import pandas as pd
import streamlit as st
import fastf1
from utils import fetch_f1_data
import fastf1.plotting as fastplt
import plotly.express as px


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

lap_pace = session.laps.pick_accurate()[['Driver', 'Stint', 'Compound', 'DriverNumber', 'LapTime']]

lap_pace['LapTime'] = lap_pace['LapTime'].dt.total_seconds()
lap_pace['Team'] = lap_pace.Driver.map(teams)

average_pace = lap_pace.groupby('Driver')['LapTime'].mean().sort_values()

colors = {}
for d in lap_pace.Driver.unique():
    team = lap_pace[lap_pace.Driver == d]['Team'].iloc[0]
    colors[team] = fastplt.get_team_color(team, session)

lap_pace['color'] = lap_pace.Team.map(colors)


keys = {}
for driv in average_pace.index.to_list():
    keys[driv] = average_pace.index.to_list().index(driv)
lap_pace = lap_pace.sort_values(by='Driver', key=lambda x: x.map(keys)).reset_index(drop=True)

color_map = dict(zip(lap_pace['Driver'], lap_pace['color']))



def create_ticks(df=lap_pace):
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
        lap_pace, 
        x="Driver", 
        y="LapTime", 
        color="Driver",
        color_discrete_map=color_map, 
        hover_data=lap_pace.columns,
        title='Pace distribution'
    )
    fig.update_traces(boxmean=True)
    fig.update_xaxes(title_text = '',
                    tickmode = 'array',
                    tickvals= list(range(len(lap_pace.Driver.unique()))),
                    ticktext = tcks,
                    tickangle=0)
    fig.update_yaxes(title_text = 'Lap Time (seconds)')

    return fig


st.plotly_chart(pace_box(tcks=create_ticks()))


def consistency():
    cons = lap_pace.groupby('Driver')['LapTime'].std().sort_values(ascending=False)
    consistency_fig = px.bar(x=cons.values, y=cons.index, color=cons.index, color_discrete_map=color_map, title='Consistency of laptimes')
    consistency_fig.update_traces(width=0.8)
    consistency_fig.update_layout(
        xaxis=dict(
            title="Standard deviation (seconds)",
            tickformat=".2f", # Format as 2 decimal places
            showgrid=True
        ),
        yaxis=dict(
            title="Drivers",
            tickfont=dict(size=14)
        )
    )
    consistency_fig.update_layout(legend_traceorder="reversed")

    return consistency_fig



cols = st.columns(2)
with cols[0]:
    st.plotly_chart(consistency())


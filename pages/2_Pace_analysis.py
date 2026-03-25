import pandas as pd
import streamlit as st
import fastf1
from utils import fetch_f1_data
import fastf1.plotting as fastplt
import plotly.express as px
import numpy as np
import datetime



# st.markdown("""
# <style>
#     .main { background-color: #0e0e0e; }
#     .stApp { background-color: #0e0e0e; color: #f0f0f0; }
#     h1, h2, h3, h4 { color: #e10600; }
#     .stSelectbox label, .stMultiSelect label, .stSlider label { color: #cccccc !important; }
#     .block-container { padding-top: 1.5rem; }
#     .fastest-lap { background-color: #6a0dad22 !important; }
#     div[data-testid="stMetricValue"] { color: #e10600; font-size: 1.4rem; }
# </style>
# """, unsafe_allow_html=True)

fastf1.Cache.enable_cache('cache')

st.set_page_config(page_title="Pace Analysis", page_icon="📈", layout="wide")

# st.markdown("# Pace Analysis")
# st.sidebar.header("Plotting Demo")

@st.cache_data(show_spinner="Loading event schedule…")
def get_schedule(year: int):
    return fastf1.get_event_schedule(year, include_testing=False)


@st.cache_data(show_spinner="Loading session…")
def load_session(year: int, location: str, session_name: str):
    session = fastf1.get_session(year, location, session_name)
    session.load(telemetry=True, weather=False, messages=False)
    return session

# ── State init ─────────────────────────────────────────────────────────────────
for key, default in [
    ("session", None),
    ("selected_drivers", []),
    ("laps_data", {}),
    ("selected_laps", {}),       # kept for delta/track map compatibility
    ("selected_lap_list", []),   # list of (driver, lap_number) tuples, max 5
    ("remove_outliers", False),
    ('selected_loc_index', 0),
    ('selected_session_index', 0)
]:
    if key not in st.session_state:
        st.session_state[key] = default


st.sidebar.markdown("## 🏎️ Session Selector")

current_year = datetime.datetime.now().year
years = list(range(2018, current_year + 1))[::-1]
year = st.sidebar.selectbox("Year", years, index=0)

schedule = get_schedule(year)
locations = schedule["EventName"].tolist()
location = st.sidebar.selectbox("Grand Prix", locations, index=st.session_state.selected_loc_index)
event_loc = location
st.session_state.selected_loc_index = locations.index(event_loc)

session_types =  schedule[schedule.EventName == event_loc][['Session1', 'Session2', 'Session3', 'Session4', 'Session5']].unstack().values.tolist()
session_name = st.sidebar.selectbox("Session", session_types, index=st.session_state.selected_session_index)
ses_name = session_name
st.session_state.selected_session_index = session_types.index(ses_name)

load_btn = st.sidebar.button("🔄 Load Session", width="stretch")

# ══════════════════════════════════════════════════════════════════════════════
# LOAD SESSION
# ══════════════════════════════════════════════════════════════════════════════
if load_btn:
    with st.spinner("Fetching data from FastF1…"):
        st.session_state.session = load_session(year, location, session_name)
        st.session_state.selected_drivers = []
        st.session_state.laps_data = {}
        st.session_state.selected_laps = {}
        st.session_state.last_tel_key = ""
        st.session_state.fig_tel_cache = None
        # Clear multiselect widget state so it resets cleanly
        for key in list(st.session_state.keys()):
            if key.startswith("driver_") or key.startswith("lap_sel_"):
                del st.session_state[key]
session = st.session_state.session

if session is None:
    st.markdown("""
    # 🏎️ F1 Telemetry Dashboard
    ### Select a year, Grand Prix and session type, then click **Load Session**.
    """)
    st.stop()
# st.dataframe(session.results)


# data setup:




# Graphs

# 1) pace boxplot of all drivers:
bst_drivers = session.results.groupby('TeamName')['Abbreviation'].first().values
driver_teams = session.results[['Abbreviation', 'TeamName']].set_index('Abbreviation').to_dict()['TeamName']
all_drivers = driver_teams.keys()




teams = session.results[['Abbreviation', 'TeamName']].set_index('Abbreviation').to_dict()['TeamName']

laps = session.laps.pick_accurate()[['Driver', 'Stint', 'Compound', 'DriverNumber', 'SpeedST', 'LapTime', 'TyreLife']]

laps['LapTime'] = laps['LapTime'].dt.total_seconds()
laps['Team'] = laps.Driver.map(teams)

average_pace = laps.groupby('Driver')['LapTime'].mean().sort_values()

team_colors = {}
driver_team = {}
# i created driver_teams up above, use it to make this better...
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
def plotly_barh(values, index, title, xlbl, ylbl, xlim, color_map):
    fig = px.bar(x=values, y=index, color=index, color_discrete_map=color_map, title=title)
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

#     fig.update_xaxes(
#     showspikes=True,        # Enable spike lines
#     spikemode="across",     # Make the line span the entire plot area
#     spikesnap="cursor",     # Snap the line to the mouse cursor instead of data points
#     spikedash="solid",      # Style of the line (e.g., 'dash', 'dot')
#     spikecolor="grey",      # Color of the cursor line
#     spikethickness=1        # Thickness of the cursor line
# )

    return fig
max_speeds = laps.groupby('Driver')['SpeedST'].max().sort_values(ascending=True)




cols = st.columns(2)
with cols[0]:
    st.plotly_chart(plotly_barh(consistency.values, consistency.index, 
                                'Driver Consistency', 
                                'Standard Deviation (\u00B1 time(s))',
                                  'Drivers', [0, consistency.max()+0.2],
                                   color_map=driver_color_map))
with cols[1]:
    st.plotly_chart(plotly_barh(max_speeds.values, max_speeds.index, 
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
    # drivers = session.results.groupby('TeamName')['Abbreviation'].first().values
    df = session.laps.pick_drivers(bst_drivers)
    best_teams = df[df['IsPersonalBest'] == True].groupby('Driver')['LapTime'].last().dt.total_seconds()

    best_teams = (((best_teams - best_teams.min())/best_teams.min())*100).sort_values(ascending=False)
    best_teams_idx =  best_teams.index
    best_teams_vals = best_teams.values
    best_teams_idx = best_teams_idx.map(driver_teams)

    st.plotly_chart(plotly_barh(best_teams_vals, best_teams_idx, 
                'Percentage differnce from fastest car',
                'Percentage Difference (%)', 'Teams', [0, best_teams_vals.max()], 
                color_map=team_colors))
    




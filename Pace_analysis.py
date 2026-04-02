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

st.logo('C://Users//moki2//Mazen Work//F1 dashboard//f1fmlogo.png', size="large")


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

def outliers(series, inverse = False):
    Q1 = series.quantile(0.25)
    Q3 = series.quantile(0.75)
    IQR = Q3-Q1

    if inverse:
        out = series[(series < (Q1 - 1.75 * IQR)) | (series > (Q3 + 1.75 * IQR))]
        out = series.drop(out.index)
    else:
        out = series[(series < (Q1 - 1.75 * IQR)) | (series > (Q3 + 1.75 * IQR))]

    return out


TYRE_COLORS = {
    "SOFT": "#e8002d",
    "MEDIUM": "#ffd700",
    "HARD": "#f0f0f0",
    "INTERMEDIATE": "#39b54a",
    "WET": "#0067ff",
    "UNKNOWN": "#888888",
    "TEST-UNKNOWN": "#888888",
}

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
st.sidebar.write('Notice: Please press load session, even if the session appears to have loaded.')


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
    col1, col2 = st.columns([6,1], gap="xxsmall") 

    with col1:
        # Display the image in the first column
         st.markdown("""
        # 🏎️ F1 Session Dashboard: <br>Presented by F1FM Analytics
         All the graphs you need to analyse F1 races and sessions all for free!
        Become your own pitwall now!
        ### Select a year, Grand Prix and session type, then click **Load Session**.
        """, unsafe_allow_html=True)

    with col2:
        st.image('C://Users//moki2//Mazen Work//F1 dashboard//f1fmlogo.png', width=200)


    st.stop()

col1, col2 = st.columns([6,1], gap="xxsmall") 
with col1:
    st.markdown(f"# 🏎️ {year} {location} — {session_name}")

with col2:
    st.image('C://Users//moki2//Mazen Work//F1 dashboard//f1fmlogo.png', width=200)


st.markdown("---")


# Graphs

# 1) pace boxplot of all drivers:
bst_drivers = session.results.groupby('TeamName')['Abbreviation'].first().values
driver_teams = session.results[['Abbreviation', 'TeamName']].set_index('Abbreviation').to_dict()['TeamName']
all_drivers = driver_teams.keys()

# driver_color_map = {}
driver_line_styles = {}
for d in list(all_drivers):
    style = fastplt.get_driver_style(d, ['color', 'linestyle'], session=session)
    if style['linestyle'] == 'dashed':
        style['linestyle'] = 'dash'
    driver_line_styles[d]= style['linestyle']
    # driver_color_map[d] = style['color']




teams = session.results[['Abbreviation', 'TeamName']].set_index('Abbreviation').to_dict()['TeamName']

laps = session.laps[['Driver', 'Stint', 'Compound', 'DriverNumber', 'SpeedST', 'LapTime', 'TyreLife', 'IsAccurate']]

laps['LapTime'] = laps['LapTime'].dt.total_seconds()
laps['Team'] = laps.Driver.map(teams)

average_pace = laps.pick_accurate().pick_quicklaps().groupby('Driver')['LapTime'].mean().sort_values()

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




COMPOUND_COLORS = {
    'S': '#FF3333',  # Soft - Red
    'M': '#FFD700',  # Medium - Yellow
    'H': '#FFFFFF',  # Hard - White
    'I': '#00CFFF',  # Inter - Green (from your palette)
    'W': '#0057FF',  # Wet - Blue
}

def create_ticks(df=laps):
    ticks = []
    df_clean = df.pick_accurate().pick_quicklaps()

    for d in df.Driver.unique():
        stnt = ''
        compounds = df[df.Driver == d][['Stint', 'Compound']].value_counts().sort_index().index

        for c in range(len(compounds)):
            letter = compounds[c][1][0]
            color = COMPOUND_COLORS.get(letter, '#AAAAAA')
            colored = f'<span style="color:{color}">{letter}</span>'
            stnt = stnt + colored + '-'

            raw_len = len(stnt.replace('-', '').replace(' ', ''))  # rough char count ignoring spans
            actual_letters = sum(1 for ch in compounds[:c+1] for x in [ch[1][0]])  # count letters added

            if actual_letters > 1 and actual_letters % 2 == 0:
                stnt = stnt[:-1] + '<br>'  # replace trailing '-' with line break

        if stnt.endswith('-'):
            stnt = stnt[:-1]
        elif stnt.endswith('<br>'):
            stnt = stnt[:-4]
        
        
        avg = df_clean[df_clean.Driver == d]['LapTime'].mean()
        bst_avg = average_pace.iloc[0]
        diff = f"+{avg - bst_avg:.3f}"
        avg = str(round(avg, 3))

        


        b = '<br>'
        tick = d + b + avg + b + diff + b + stnt
        ticks.append(tick)

    return ticks
    



def pace_box(tcks = average_pace.index):
# 1. Create the color mapping dictionary {Driver: HexCode}

    # 2. Generate the plot
    fig = px.box(
        laps.pick_accurate().pick_quicklaps(), 
        x="Driver", 
        y="LapTime", 
        color="Driver",
        color_discrete_map=driver_color_map, 
        hover_data=laps.columns,
        title='Pace distribution', points=False
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
        l=20,  # Left margin
        r=20,  # Right margin
        t=40,  # Top margin (leave a bit for the title if needed)
        b=10   # Bottom margin
    ),
    # autosize=True
)

    return fig


st.plotly_chart(pace_box(tcks=create_ticks()))
st.markdown("---")

consistency = laps.pick_accurate().pick_quicklaps().groupby('Driver')['LapTime'].std().sort_values(ascending=False)
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
max_speeds = laps.groupby('Driver')['SpeedST'].max().dropna().sort_values(ascending=True)




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
fastest20['LapNumber'] = fastest20['LapNumber'].astype('int')
fastest20['TyreLife'] = fastest20['TyreLife'].astype('int')


def apply_team_colors(column):
    # Map the team name to the hex code, default to empty string if not found
        return [f'background-color: {team_colors.get(t, "")}' for t in column]


st.markdown('---')
cols = st.columns(2)
with cols[0]:
    st.markdown(f'<h4> Fastest Laps of {ses_name}</h4>', unsafe_allow_html=True)
    st.dataframe(fastest20.style.apply(apply_team_colors, subset=['Team']))
with cols[1]:
    # drivers = session.results.groupby('TeamName')['Abbreviation'].first().values
    # st.write(ses_name)
    if (ses_name == 'Race') or (ses_name == 'Sprint'):
        best_teams = laps.pick_accurate().pick_quicklaps().groupby('Team')['LapTime'].mean().sort_values(ascending=True)
        title = 'Average Differnce from Best Pace'
        
    else:
        best_teams = laps.groupby('Team')['LapTime'].min()
        title = 'Lap Time Differnce from Fastest Car'

    best_teams = ((best_teams - best_teams.min())).sort_values(ascending=False)
    # best_teams = best_teams.sort_values(asc)
    best_teams_idx =  best_teams.index
    best_teams_vals = best_teams.values

    st.plotly_chart(plotly_barh(best_teams_vals, best_teams_idx, 
                title,
                'Lap Time Difference (s/L)', 'Teams', [0, best_teams_vals.max()], 
                color_map=team_colors))
    
if (ses_name == 'Race') or ses_name == 'Sprint':
    lap_ends = session.laps
    lap_ends['LapEndTime'] = lap_ends['LapStartTime'] + lap_ends['LapTime']
    lap_ends['LapEndTime'] = lap_ends['LapEndTime'].dt.total_seconds()
    lap_ends = lap_ends.groupby(['Driver', 'LapNumber'])['LapEndTime'].first().unstack()

    idx_finish = session.results[session.results.Time.isnull() == False].Abbreviation.values

    lap_ends.loc[idx_finish, :] = lap_ends.loc[idx_finish, :].interpolate('linear', axis=1)
    lap_diff = (lap_ends.min() - lap_ends).T
    lap_diff.reset_index(drop=True, inplace=True)
    # lap_diff.index = lap_diff.index+1

    fig = px.line(
        lap_diff, 
        x=lap_diff.index, 
        y=lap_diff.columns,
        color_discrete_map=driver_color_map
    )

    # Optional: Update axis labels if the index name is missing
    fig.update_layout(xaxis_title="Lap Number", yaxis_title="Time Difference from leader",  hovermode="x unified")
                    #   hovertemplate="<b>%{data.name} %{y}<extra></extra>")
    fig.update_traces(hovertemplate="<b>%{data.name} Gap to leader: %{y}<extra></extra>")


    driver_cols = list(lap_diff.columns) 

    # If you are filtering columns in a loop or list comprehension:
    desired_order = list(session.results.Abbreviation.values)
    ordered_cols = [c for c in lap_diff.columns if c in desired_order]

    # 3. Apply ordering and visibility logic
    for trace in fig.data:
        if trace.name in driver_line_styles:
            trace.update(line=dict(dash=driver_line_styles[trace.name]))

        if trace.name in desired_order:
            # Set the rank based on the index in your list
            trace.legendrank = desired_order.index(trace.name)
        else:
            # Drivers not in your list go to the end
            trace.legendrank = 1000 
        
        # Hide all traces except the first one in your desired order
        if trace.name != desired_order[0]:
            trace.visible = 'legendonly'

    # fig.update_layout(
    #     template="plotly_dark",
    #     legend=dict(bgcolor="#1a1a1a", bordercolor="#333"),
    #     margin=dict(l=60, r=20, t=30, b=40),
    #     hovermode="x",
    #     hoverlabel=dict(
    #         bgcolor="#1a1a1a",
    #         bordercolor="#444",
    #         font=dict(color="#f0f0f0", size=12),
    #         namelength=-1,
    #     ),
    # )

    st.markdown("---")
    st.plotly_chart(fig)


st.markdown("---")
st.markdown(
    "<center style='color:#aaaaaa;font-size:0.85rem;'>Data provided by <b>FastF1</b> · Built with <b>Streamlit</b> & <b>Plotly</b></center>",
    unsafe_allow_html=True,
)

st.markdown(
    "<center style='color:#555;font-size:0.8rem;'>" \
    "This is an unofficial, non-commercial project and "
    "is not affiliated with the FIA or Formula 1. All F1-related trademarks"
    " and copyrights belong to their respective owners."
    "</center>",
    unsafe_allow_html=True,
)


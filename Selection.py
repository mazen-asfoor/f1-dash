import streamlit as st
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import fastf1
import fastf1.plotting as fastplt
import datetime

from utils import fetch_f1_data



st.markdown("""
<style>
    .main { background-color: #0e0e0e; }
    .stApp { background-color: #0e0e0e; color: #f0f0f0; }
    h1, h2, h3, h4 { color: #e10600; }
    .stSelectbox label, .stMultiSelect label, .stSlider label { color: #cccccc !important; }
    .block-container { padding-top: 1.5rem; }
    .fastest-lap { background-color: #6a0dad22 !important; }
    div[data-testid="stMetricValue"] { color: #e10600; font-size: 1.4rem; }
</style>
""", unsafe_allow_html=True)

# fastf1 setup
fastf1.Cache.enable_cache('cache')


# page setup:
st.set_page_config(page_title='F1 Dashboard/Summary', layout="wide")

years = range(2018, datetime.datetime.now().year+1, 1)
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


@st.cache_data(show_spinner="Loading event schedule…")
def get_schedule(year: int):
    return fastf1.get_event_schedule(year, include_testing=False)


@st.cache_data(show_spinner="Loading session…")
def load_session(year: int, location: str, session_name: str):
    session = fastf1.get_session(year, location, session_name)
    session.load(telemetry=True, weather=False, messages=False)
    return session

# page layout:
welcome = st.title('F1 Insightfully: F1 Session Dashboard')


# with st.form(key='select_event'):
# cols = st.columns(3)
# with cols[0]:
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

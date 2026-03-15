import pandas as pd
import streamlit as st
import fastf1
from utils import fetch_f1_data


fastf1.Cache.enable_cache('cache')

st.set_page_config(page_title="Summary", page_icon="📊", layout="wide")

st.markdown("# Session Summary")
# st.sidebar.header("Plotting Demo")



session = fetch_f1_data(st.session_state.selected_year, st.session_state.gp, st.session_state.event[0])
st.dataframe(session.results)


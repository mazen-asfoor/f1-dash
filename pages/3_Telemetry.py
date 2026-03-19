import pandas as pd
import streamlit as st
import fastf1
from utils import fetch_f1_data

fastf1.Cache.enable_cache('cache')
session = fetch_f1_data(st.session_state.selected_year, st.session_state.gp, st.session_state.event[0])



st.set_page_config(page_title="Telemetry", page_icon="📈", layout="wide")

st.markdown("# Telemetry analysis")
# st.sidebar.header("Plotting Demo")

# import streamlit as st

all_drivers = session.results['Abbreviation'].values.tolist()

# Initialize session state for selected items if not present
if "selected_items" not in st.session_state:
    st.session_state.selected_items = []

def select_all_callback():
    """Callback to select all items."""
    st.session_state.selected_items = all_drivers.copy()

def deselect_all_callback():
    """Callback to deselect all items."""
    st.session_state.selected_items = []

# Display the multiselect widget
st.multiselect(
    "Select Items:",
    options=all_drivers,
    key="selected_items", # Link the widget to the session state variable
)

# Buttons to automate the selection
cols = st.columns(2, width=250, gap='xsmall')

with cols[0]:
    st.button("Select All", on_click=select_all_callback)
with cols[1]:
    st.button("Deselect All", on_click=deselect_all_callback)

# Display the result
st.write("You selected:", st.session_state.selected_items)

import streamlit as st
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import fastf1
import fastf1.plotting as fastplt
import datetime

from utils import fetch_f1_data

# fastf1 setup
fastf1.Cache.enable_cache('cache')


# page setup:
st.set_page_config(page_title='F1 Dashboard/Summary', layout="wide")

years = range(2000, datetime.datetime.now().year+1, 1)
if 'default_year' not in st.session_state:
    # Set the initial default value to the first option
    st.session_state.default_year = years[-1] 


# functions:



# page layout:
welcome = st.title('Hello World')


# with st.form(key='select_event'):
cols = st.columns(3)
with cols[0]:
    year_selected = st.selectbox('Year:', years, 0, key='default_year')
    st.session_state.selected_year = year_selected

schedule = fastf1.get_event_schedule(year_selected)

with cols[1]:
    locs = schedule[schedule.EventFormat != 'testing']["Location"].to_list()
    location =st.selectbox('Location:', locs, 0, key='location')
    st.session_state.gp = location


with cols[2]:
    race = ['Qualifying', 'Race']
    event = st.selectbox('Session:', race, 0, key='session')
    st.session_state.event = event


pressed = st.button('Initiate dashboard')

if 'default_year' not in st.session_state:
    # Set the initial default value to the first option
    st.session_state.default_year = years[-1]
    

# if st.button("Go to Page Two"):
    
if pressed:
    with st.spinner('This may take a couple of seconds...'):
        session = fetch_f1_data(year_selected, location, event[0])
        st.switch_page("pages/1_Summary.py")
    # st.dataframe(session.results)

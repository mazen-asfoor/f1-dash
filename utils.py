import pandas as pd
import fastf1
import streamlit as st
import datetime

@st.cache_data
def fetch_f1_data(y=datetime.datetime.now().year, name='1', session_type='R'):
    s = fastf1.get_session(y, name, session_type)
    s.load()
    return s
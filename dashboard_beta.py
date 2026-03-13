import streamlit as st
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import fastf1

import fastf1.plotting as fastplt


st.title('Hello World')
x = st.slider('slide', 1.0, 10.0, step=0.01)
# x = st.text_input('enter value')
cols = st.columns(2)
with cols[0]:
    lst = ['HAM', 'VER', 'ANT', 'BER', 'LIN']
    driver1 =st.selectbox('Choose driver 1:', lst, 0, key='driver1_dropdown_list')
    st.write(driver1)

with cols[1]:
    lst = ['HAM', 'VER', 'ANT', 'BER', 'LIN']
    driver2 =st.selectbox('Choose driver 1:', lst, 0, key='driver2_dropdown_list')
    st.write(driver2)

# fastf1.Cache.enable_cache('cache')

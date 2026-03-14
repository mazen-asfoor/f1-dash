import pandas as pd
import streamlit as st
import fastf1

fastf1.Cache.enable_cache('cache')

st.set_page_config(page_title="Plotting Demo", page_icon="📈", layout="wide")

st.markdown("# Plotting Demo")
st.sidebar.header("Plotting Demo")


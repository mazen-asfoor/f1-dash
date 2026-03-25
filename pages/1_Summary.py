import pandas as pd
import streamlit as st
import fastf1
from utils import fetch_f1_data
from utils import fix_laps


fastf1.Cache.enable_cache('cache')

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

st.set_page_config(page_title="Summary", page_icon="📊", layout="wide")

st.markdown("# Session Summary")
# st.sidebar.header("Plotting Demo")



session = st.session_state.session

laps_data = fix_laps(session)

if 'Q' in st.session_state.event[0]:
    result_table = session.results[['Abbreviation', 'TeamName', 'Q1', 'Q2', 'Q3', 'Position']]
    
    rank_map = {v: k for k, v in result_table['Abbreviation'].reset_index(drop=True).to_dict().items()}

    
    # Apply the sort using that mapping
    result_table['Gap'] = (laps_data.groupby('Driver')['LapTime'].min().sort_index(key=lambda x: x.map(rank_map))).values
    result_table['OfficialTimes'] = (laps_data.groupby('Driver')['LapTime'].min().sort_index(key=lambda x: x.map(rank_map))).values

    
    result_table['Gap'] = result_table['Gap'].dt.total_seconds()
    result_table['Gap'] = result_table['Gap'] - result_table['Gap'].iloc[0]

    result_table['Gap'] = result_table['Gap'].apply(lambda x: '%+.2f' % x)

    result_table['Q1'] = result_table['Q1'].apply(lambda x: str(x)[10:])
    result_table['Q2'] = result_table['Q2'].apply(lambda x: str(x)[10:])
    result_table['Q3'] = result_table['Q3'].apply(lambda x: str(x)[10:])

    result_table['OfficialTimes'] = result_table['OfficialTimes'].apply(lambda x: str(x)[10:])

    # result_table.Position = result_table.Position.astype(int)
    result_table = result_table[['Abbreviation', 'TeamName', 'Q1', 'Q2', 'Q3', 'OfficialTimes', 'Gap', 'Position']]
else:
    result_table = session.results[['Abbreviation', 'TeamName', 'ClassifiedPosition', 'Points']]


    result_table['ClassifiedPosition'] = result_table['ClassifiedPosition'].replace('R', 'DNF')
    result_table['ClassifiedPosition'] = result_table['ClassifiedPosition'].replace('W', 'DNS')
    result_table['ClassifiedPosition'] = result_table['ClassifiedPosition'].replace('D', 'DSQ')

    result_table['FastestLap'] = ''

    idx_fastest = result_table[result_table.Abbreviation == session.laps.pick_fastest().Driver].index
    result_table.loc[idx_fastest, 'FastestLap'] = True

st.dataframe(result_table)


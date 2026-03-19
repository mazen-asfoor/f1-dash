import pandas as pd
import fastf1
import streamlit as st
import datetime
import numpy as np

@st.cache_data
def fetch_f1_data(y=datetime.datetime.now().year, name='1', session_type='R'):
    s = fastf1.get_session(y, name, session_type)
    s.load()
    return s


def fix_laps(sess):
    # 1. Identify missing drivers
    laps_drivers = set(sess.laps['Driver'].unique())
    results_drivers = set(sess.results['Abbreviation'])
    missing_drivers = results_drivers - laps_drivers

    # 2. Create a list of dictionaries for the new rows
    new_rows = []
    for driver in missing_drivers:
        # Create a template with np.nan for all required columns
        row = {col: np.nan for col in sess.laps.columns}
        
        # Update the specific Driver identifier
        row['Driver'] = driver
        
        # Optionally: Pull the DriverNumber from session.results if needed
        driver_info = sess.results[sess.results['Abbreviation'] == driver]
        if not driver_info.empty:
            row['DriverNumber'] = driver_info['DriverNumber'].iloc[0]
            row['Team'] = driver_info['TeamName'].iloc[0]
        
        new_rows.append(row)

    # 3. Append to the existing DataFrame
    # if new_rows:
    new_laps_df = pd.DataFrame(new_rows)
    lap_data = pd.concat([sess.laps, new_laps_df], ignore_index=True)

    return lap_data
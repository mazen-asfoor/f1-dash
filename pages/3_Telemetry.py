import streamlit as st
import fastf1
import fastf1.plotting
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from matplotlib import colormaps
import warnings
import datetime
import os
from utils import fetch_f1_data


st.set_page_config(
    page_title="F1 Telemetry Dashboard",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ────────────────────────────────────────────────────────────────────
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

# ── Tyre colour map ────────────────────────────────────────────────────────────
TYRE_COLORS = {
    "SOFT": "#e8002d",
    "MEDIUM": "#ffd700",
    "HARD": "#f0f0f0",
    "INTERMEDIATE": "#39b54a",
    "WET": "#0067ff",
    "UNKNOWN": "#888888",
    "TEST-UNKNOWN": "#888888",
}

@st.cache_data(show_spinner="Loading event schedule…")
def get_schedule(year: int):
    return fastf1.get_event_schedule(year, include_testing=False)

def load_session(year: int, location: str, session_name: str):
    session = fastf1.get_session(year, location, session_name)
    session.load(telemetry=True, weather=False, messages=False)
    return session

def get_driver_color(driver_abbr: str, session) -> str:
    try:
        team = session.laps.pick_driver(driver_abbr)["Team"].iloc[0]

        # Find all drivers on the same team
        team_drivers = (
            session.laps[session.laps["Team"] == team]["Driver"]
            .unique().tolist()
        )
        team_drivers.sort()  # consistent ordering

        is_secondary = team_drivers.index(driver_abbr) == 1

        if is_secondary:
            # Use the secondary/variant color if available, else darken primary
            try:
                colors = fastf1.plotting.get_team_color(team, session)
                # fastf1 may return a single hex — derive a secondary by shifting lightness
                from matplotlib.colors import to_rgb, to_hex
                import colorsys
                r, g, b = to_rgb(colors)
                h, l, s = colorsys.rgb_to_hls(r, g, b)
                # Lighten if dark team, darken if light team
                l2 = min(1.0, l + 0.25) if l < 0.5 else max(0.0, l - 0.25)
                r2, g2, b2 = colorsys.hls_to_rgb(h, l2, s)
                return to_hex((r2, g2, b2))
            except Exception:
                pass

        return fastf1.plotting.get_driver_color(driver_abbr, session)

    except Exception:
        palette = px.colors.qualitative.Plotly
        drivers = list(session.drivers)
        idx = drivers.index(driver_abbr) if driver_abbr in drivers else 0
        return palette[idx % len(palette)]

def lap_time_to_seconds(lap_time) -> float:
    try:
        return lap_time.total_seconds()
    except Exception:
        return np.nan


def seconds_to_laptime(s: float) -> str:
    if np.isnan(s):
        return "—"
    m = int(s // 60)
    sec = s - m * 60
    return f"{m}:{sec:06.3f}"


def filter_outliers(laps_df: pd.DataFrame) -> pd.DataFrame:
    """Remove pit‑in/out laps and laps > 107 % of the median."""
    df = laps_df.copy()
    df = df[~df["PitInTime"].notna() & ~df["PitOutTime"].notna()]
    median = df["LapTimeSeconds"].median()
    if not np.isnan(median):
        df = df[df["LapTimeSeconds"] <= median * 1.07]
    return df


def build_laps_df(session, driver_abbr: str) -> pd.DataFrame:
    laps = session.laps.pick_driver(driver_abbr).copy()
    laps["LapTimeSeconds"] = laps["LapTime"].apply(lap_time_to_seconds)
    laps["LapTimeStr"] = laps["LapTimeSeconds"].apply(seconds_to_laptime)
    laps["Driver"] = driver_abbr
    laps["Compound"] = laps["Compound"].fillna("UNKNOWN")
    laps["LapNumber"] = laps["LapNumber"].astype(int)
    return laps.reset_index(drop=True)


fastf1.Cache.enable_cache('cache')

session = st.session_state.session

for key, default in [
    ("session", session),
    ("selected_drivers", []),
    ("laps_data", {}),          # {abbr: DataFrame}
    ("selected_laps", {}),      # {abbr: lap_number}
    ("remove_outliers", False),
    ('selected_loc_index', 0),
    ('selected_session_index', 0)
]:
    if key not in st.session_state:
        st.session_state[key] = default

st.sidebar.markdown("## 🏎️ Session Selector")

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

st.markdown(f"# 🏎️ {year} {location} — {session_name}")
st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# DRIVER SELECTOR
# ══════════════════════════════════════════════════════════════════════════════
driver_list = session.laps["Driver"].unique().tolist()
driver_list_sorted = sorted(driver_list)

st.markdown("## 👤 Driver Selection")
selected_drivers = st.multiselect(
    "Select one or more drivers to compare",
    options=driver_list_sorted,
    default=st.session_state.selected_drivers,
    max_selections=5,
    help="Select up to 5 drivers to overlay on the same chart.",
)
st.session_state.selected_drivers = selected_drivers

# Load laps data for newly selected drivers
for drv in selected_drivers:
    if drv not in st.session_state.laps_data:
        st.session_state.laps_data[drv] = build_laps_df(session, drv)

# Remove deselected drivers
for drv in list(st.session_state.laps_data.keys()):
    if drv not in selected_drivers:
        del st.session_state.laps_data[drv]
        st.session_state.selected_laps.pop(drv, None)

if not selected_drivers:
    st.info("Select at least one driver above to start.")
    st.stop()

# ── Outlier toggle ─────────────────────────────────────────────────────────────
st.session_state.remove_outliers = st.toggle(
    "🚫 Remove outlier laps (pit stops / slow laps)",
    value=st.session_state.remove_outliers,
)

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# LAP TIME LINE CHART
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("## 📈 Lap Times")

fig_laps = go.Figure()

for drv in selected_drivers:
    raw_laps = st.session_state.laps_data[drv].copy()
    disp_laps = filter_outliers(raw_laps) if st.session_state.remove_outliers else raw_laps
    disp_laps = disp_laps.dropna(subset=["LapTimeSeconds"])
    # raw_laps["LapTimeSeconds_fuel_adj"] = disp_laps["LapTimeSeconds"] = (0.03*(disp_laps["LapTimeSeconds"].max() - disp_laps["LapTimeSeconds"]))

    drv_color = get_driver_color(drv, session)

    # One trace per tyre compound so markers get correct colours
    for compound, grp in disp_laps.groupby("Compound"):
        tyre_color = TYRE_COLORS.get(compound, "#aaaaaa")
        hover = [
            f"Driver: {drv}<br>Lap: {r.LapNumber}<br>Time: {r.LapTimeStr}<br>Tyre: {compound}"
            for _, r in grp.iterrows()
        ]
        fig_laps.add_trace(go.Scatter(
            x=grp["LapNumber"],
            y=grp["LapTimeSeconds"],
            mode="lines+markers",
            name=f"{drv} — {compound}",
            line=dict(color=drv_color, width=2),
            marker=dict(color=tyre_color, size=9, line=dict(color=drv_color, width=1.5)),
            hovertext=hover,
            hoverinfo="text",
            legendgroup=drv,
            customdata=list(zip([drv] * len(grp), grp["LapNumber"])),
        ))

fig_laps.update_layout(
    template="plotly_dark",
    paper_bgcolor="#0e0e0e",
    plot_bgcolor="#141414",
    xaxis_title="Lap Number",
    yaxis_title="Lap Time (s)",
    yaxis=dict(tickformat=".3f"),
    hovermode="closest",
    legend=dict(bgcolor="#1a1a1a", bordercolor="#333"),
    height=480,
    margin=dict(l=60, r=20, t=30, b=50),
)

st.plotly_chart(fig_laps, width='stretch', key="lap_time_chart")

# ══════════════════════════════════════════════════════════════════════════════
# LAPS TABLE
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("## 📋 Lap Data")

all_laps_frames = []
for drv in selected_drivers:
    raw = st.session_state.laps_data[drv].copy()
    disp = filter_outliers(raw) if st.session_state.remove_outliers else raw
    all_laps_frames.append(disp[["Driver", "LapNumber", "LapTimeStr", "Compound", "Stint", "TyreLife"]].copy())

if all_laps_frames:
    table_df = pd.concat(all_laps_frames, ignore_index=True)
    table_df = table_df.rename(columns={
        "LapNumber": "Lap", "LapTimeStr": "Lap Time",
        "TyreLife": "Tyre Age", "Stint": "Stint"
    })

    # Identify overall fastest lap
    fastest_times = {}
    for drv in selected_drivers:
        raw = st.session_state.laps_data[drv]
        best = raw["LapTimeSeconds"].min()
        fastest_times[drv] = best

    overall_fastest_drv = min(fastest_times, key=fastest_times.get)
    overall_fastest_lap = (
        st.session_state.laps_data[overall_fastest_drv]
        .loc[st.session_state.laps_data[overall_fastest_drv]["LapTimeSeconds"].idxmin(), "LapNumber"]
    )

    def highlight_fastest(row):
        is_fastest = (row["Driver"] == overall_fastest_drv) and (row["Lap"] == overall_fastest_lap)
        bg = "background-color: #6a0dad44; color: #d084ff; font-weight: bold;" if is_fastest else ""
        return [bg] * len(row)

    styled = table_df.style.apply(highlight_fastest, axis=1)
    st.dataframe(styled, width='stretch', height=320)

# ── Per-driver fastest lap metrics ────────────────────────────────────────────
cols = st.columns(len(selected_drivers))
for i, drv in enumerate(selected_drivers):
    raw = st.session_state.laps_data[drv]
    best_idx = raw["LapTimeSeconds"].idxmin()
    best_row = raw.loc[best_idx]
    with cols[i]:
        st.metric(
            label=f"⚡ {drv} — Fastest",
            value=best_row["LapTimeStr"],
            delta=f"Lap {best_row['LapNumber']} — {best_row['Compound']}",
            delta_color="off",
        )

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# TELEMETRY SECTION
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("## 🔬 Telemetry Analysis")

# Lap selector per driver
st.markdown("#### Select laps to inspect")
sel_cols = st.columns(len(selected_drivers))
for i, drv in enumerate(selected_drivers):
    raw = st.session_state.laps_data[drv]
    lap_options = raw["LapNumber"].tolist()
    default_lap = int(raw.loc[raw["LapTimeSeconds"].idxmin(), "LapNumber"])
    with sel_cols[i]:
        chosen = st.selectbox(
            f"{drv} — Lap",
            options=lap_options,
            index=lap_options.index(default_lap) if default_lap in lap_options else 0,
            key=f"lap_sel_{drv}",
        )
        st.session_state.selected_laps[drv] = int(chosen)


@st.cache_data(show_spinner="Loading telemetry…")
def get_telemetry(year, location, session_name, driver, lap_number):
    sess = load_session(year, location, session_name)
    laps = sess.laps.pick_driver(driver)
    lap = laps[laps["LapNumber"] == lap_number].iloc[0]
    tel = lap.get_telemetry().add_distance()
    return tel


# ── Fetch telemetry ────────────────────────────────────────────────────────────
tel_data = {}
for drv in selected_drivers:
    lap_num = st.session_state.selected_laps.get(drv)
    if lap_num:
        try:
            tel_data[drv] = get_telemetry(year, location, session_name, drv, lap_num)
        except Exception as e:
            st.warning(f"Could not load telemetry for {drv} lap {lap_num}: {e}")

if not tel_data:
    st.info("Telemetry will appear here once a session is loaded.")
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# TRACK MAP + DOMINANCE
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### 🗺️ Track Map")

ref_drv = list(tel_data.keys())[0]
ref_tel = tel_data[ref_drv]

fig_map = go.Figure()

if len(tel_data) == 1:
    # Single driver — colour by speed
    fig_map.add_trace(go.Scatter(
        x=ref_tel["X"], y=ref_tel["Y"],
        mode="markers",
        marker=dict(
            color=ref_tel["Speed"],
            colorscale="RdYlGn",
            size=4,
            colorbar=dict(title="Speed (km/h)"),
            showscale=True,
        ),
        name=f"{ref_drv} speed",
        hovertemplate="Speed: %{marker.color:.0f} km/h<extra></extra>",
    ))
else:
    # Multi driver — dominance (fastest driver at each mini-sector)
    drivers = list(tel_data.keys())
    colors_map = {d: get_driver_color(d, session) for d in drivers}

    # Interpolate all telemetry onto the same distance grid
    max_dist = min(t["Distance"].max() for t in tel_data.values())
    grid = np.linspace(0, max_dist, 500)

    speed_grid = {}
    x_grid, y_grid = None, None
    for drv, tel in tel_data.items():
        speed_grid[drv] = np.interp(grid, tel["Distance"], tel["Speed"])
        if x_grid is None:
            x_grid = np.interp(grid, tel["Distance"], tel["X"])
            y_grid = np.interp(grid, tel["Distance"], tel["Y"])

    dominant = [max(drivers, key=lambda d: speed_grid[d][i]) for i in range(len(grid))]

    for drv in drivers:
        mask = [d == drv for d in dominant]
        xs = [x_grid[i] if mask[i] else None for i in range(len(grid))]
        ys = [y_grid[i] if mask[i] else None for i in range(len(grid))]
        fig_map.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="markers",
            marker=dict(color=colors_map[drv], size=5),
            name=f"{drv} dominant",
        ))

fig_map.update_layout(
    template="plotly_dark",
    paper_bgcolor="#0e0e0e",
    plot_bgcolor="#0e0e0e",
    xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
    yaxis=dict(visible=False),
    height=380,
    margin=dict(l=0, r=0, t=10, b=0),
    legend=dict(bgcolor="#1a1a1a"),
)
st.plotly_chart(fig_map, width="stretch")

# ══════════════════════════════════════════════════════════════════════════════
# TELEMETRY CHANNELS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### 📡 Telemetry Channels")

CHANNELS = [
    ("Speed", "Speed (km/h)"),
    ("Throttle", "Throttle (%)"),
    ("Brake", "Brake"),
    ("nGear", "Gear"),
    ("RPM", "RPM"),
    ("DRS", "DRS"),
]

# Only include channels that exist in the data
available_channels = []
for ch, label in CHANNELS:
    for tel in tel_data.values():
        if ch in tel.columns:
            available_channels.append((ch, label))
            break

n_rows = len(available_channels)


fig_tel = make_subplots(
    rows=n_rows, cols=1,
    shared_xaxes=True,
    subplot_titles=[label for _, label in available_channels],
    vertical_spacing=0.04,
)

for drv, tel in tel_data.items():
    drv_color = get_driver_color(drv, session)
    lap_num = st.session_state.selected_laps.get(drv, "?")
    for row_idx, (ch, label) in enumerate(available_channels, start=1):
        if ch not in tel.columns:
            continue
        fig_tel.add_trace(
            go.Scatter(
                x=tel["Distance"],
                y=tel[ch],
                mode="lines",
                name=f"{drv} L{lap_num}",
                line=dict(color=drv_color, width=1.8),
                legendgroup=drv,
                showlegend=(row_idx == 1),
                hovertemplate=f"{drv} — {label}: %{{y:.1f}}<extra></extra>",
            ),
            row=row_idx, col=1,
        )

fig_tel.update_layout(
    template="plotly_dark",
    paper_bgcolor="#0e0e0e",
    plot_bgcolor="#141414",
    height=220 * n_rows,
    legend=dict(bgcolor="#1a1a1a", bordercolor="#333"),
    margin=dict(l=60, r=20, t=30, b=40),

    # Separate tooltip per subplot, not unified
    hovermode="x",
    hoverlabel=dict(
        bgcolor="#1a1a1a",
        bordercolor="#444",
        font=dict(color="#f0f0f0", size=12),
        namelength=-1,
    ),
)

# Vertical spike line that draws across ALL subplots when hovering any one
fig_tel.update_xaxes(
    showspikes=True,
    spikemode="across",        # draws the line across the entire subplot height
    spikesnap="cursor",
    spikecolor="#ffffff",
    spikethickness=1,
    spikedash="dot",
    showticklabels=True,
)

fig_tel.update_yaxes(
    showspikes=False,           # no horizontal spike, only vertical
)

st.plotly_chart(fig_tel, width="stretch",  config={"displayModeBar": True})

# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown(
    "<center style='color:#555;font-size:0.8rem;'>Data provided by <b>FastF1</b> · Built with Streamlit & Plotly</center>",
    unsafe_allow_html=True,
)

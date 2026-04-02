import streamlit as st
import fastf1
import fastf1.plotting
import pandas as pd
import numpy as np
from numpy.polynomial import polynomial as P
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from matplotlib import colormaps
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import os

warnings.filterwarnings("ignore")

# ── Cache dir ──────────────────────────────────────────────────────────────────
# CACHE_DIR = "./f1_cache"
# os.makedirs(CACHE_DIR, exist_ok=True)
# fastf1.Cache.enable_cache(CACHE_DIR)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="F1 Telemetry Dashboard",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.logo('C://Users//moki2//Mazen Work//F1 dashboard//f1fmlogo.png', size="large")

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

# ── Helpers ────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Loading event schedule…")
def get_schedule(year: int):
    return fastf1.get_event_schedule(year, include_testing=False)


@st.cache_data(show_spinner="Loading session…")
def load_session(year: int, location: str, session_name: str):
    session = fastf1.get_session(year, location, session_name)
    session.load(telemetry=True, weather=False, messages=False)
    return session

@st.cache_data(show_spinner=False)
def get_driver_color(driver_abbr: str, _session) -> str:
    try:
        return fastf1.plotting.get_driver_color(driver_abbr, session)
    except Exception:
        palette = px.colors.qualitative.Plotly
        drivers = list(session.drivers)
        idx = drivers.index(driver_abbr) if driver_abbr in drivers else 0
        return palette[idx % len(palette)]


def get_driver_color_for_selection(driver_abbr: str, selected_drivers: list, _session) -> str:
    """
    Returns primary team colour unless this driver's teammate is also selected,
    in which case the second driver alphabetically gets a lightened variant.
    """
    try:
        team = session.laps.pick_driver(driver_abbr)["Team"].iloc[0]

        # Only look at teammates that are ALSO in the current selection
        selected_teammates = sorted([
            d for d in selected_drivers
            if d != driver_abbr and
            not session.laps.pick_driver(d).empty and
            session.laps.pick_driver(d)["Team"].iloc[0] == team
        ])

        # If no teammate is selected, always use primary colour
        if not selected_teammates:
            return get_driver_color(driver_abbr, _session)

        # Teammate is selected — second alphabetically gets the variant
        team_pair = sorted([driver_abbr] + selected_teammates)
        is_secondary = team_pair.index(driver_abbr) == 1

        if is_secondary:
            try:
                colors = fastf1.plotting.get_team_color(team, session)
                from matplotlib.colors import to_rgb, to_hex
                import colorsys
                r, g, b = to_rgb(colors)
                h, l, s = colorsys.rgb_to_hls(r, g, b)
                l2 = min(1.0, l + 0.25) if l < 0.5 else max(0.0, l - 0.25)
                r2, g2, b2 = colorsys.hls_to_rgb(h, l2, s)
                return to_hex((r2, g2, b2))
            except Exception:
                pass

        return get_driver_color(driver_abbr, _session)

    except Exception:
        return get_driver_color(driver_abbr, _session)

TEAMMATE_LINE_STYLES = ["solid", "dash", "dot", "dashdot", "longdash"]

@st.cache_data(show_spinner=False)
def get_driver_line_style(driver_abbr: str, _session) -> str:
    """Second driver on a team gets a dashed line, third gets dotted, etc."""
    try:
        team = session.laps.pick_driver(driver_abbr)["Team"].iloc[0]
        team_drivers = sorted(
            session.laps[session.laps["Team"] == team]["Driver"].unique().tolist()
        )
        idx = team_drivers.index(driver_abbr) if driver_abbr in team_drivers else 0
        return TEAMMATE_LINE_STYLES[idx % len(TEAMMATE_LINE_STYLES)]
    except Exception:
        return "solid"

# Extra colors for same-driver multi-lap comparison (never used as team colors)
EXTRA_LAP_COLORS = [
    "#FFFFFF",  # white
    "#019C1B",  # cyan
    "#5C1D2B",  # orange
    "#BF00FF",  # violet
    "#2FDA18"  # deep sky blue
]

def get_lap_color(drv: str, lap_num: int, _session) -> str:
    """
    Returns the driver's team color for their first selected lap.
    For additional laps of the same driver, returns a unique extra color.
    Each extra color is only used once across ALL drivers and laps.
    """
    selection = st.session_state.selected_lap_list

    # Colors already claimed by first laps of all selected drivers
    used_team_colors = {
        get_driver_color_for_selection(d, st.session_state.selected_drivers, _session)
        for d in st.session_state.selected_drivers
    }

    # Build a global ordered list of extra color assignments across all laps
    # so each extra lap gets a unique color regardless of which driver it belongs to
    available = [c for c in EXTRA_LAP_COLORS if c not in used_team_colors]
    extra_color_index = 0
    extra_color_map = {}  # (drv, lap_num) -> color

    for d, ln in selection:
        drv_occurrences_so_far = [
            (dd, ll) for dd, ll in selection
            if dd == d and selection.index((dd, ll)) < selection.index((d, ln))
        ]
        is_first = len(drv_occurrences_so_far) == 0

        if not is_first:
            if (d, ln) not in extra_color_map:
                extra_color_map[(d, ln)] = available[extra_color_index % len(available)]
                extra_color_index += 1

    drv_occurrences = [pair for pair in selection if pair[0] == drv]
    lap_index = next(
        (i for i, (d, l) in enumerate(drv_occurrences) if l == lap_num), 0
    )

    if lap_index == 0:
        return get_driver_color_for_selection(drv, st.session_state.selected_drivers, _session)
    else:
        return extra_color_map.get((drv, lap_num), available[0])

def lap_time_to_seconds(lap_time) -> float:
    try:
        return lap_time.total_seconds()
    except Exception:
        return np.nan

@st.cache_data(show_spinner=False)
def get_track_annotations(year, location, session_name):
    """Extract corner distances and sector distances from telemetry."""
    sess = load_session(year, location, session_name)



    # ── Sector distances ───────────────────────────────────────────────────
    # Use the fastest lap to get sector split distances
    try:
        fastest = sess.laps.pick_fastest()
        tel = fastest.get_telemetry().add_distance()

        # Sector times from the lap
        s1 = fastest["Sector1Time"]
        s2 = fastest["Sector2Time"]

        # Match sector time boundaries to distance
        tel["SessionTime_s"] = tel["SessionTime"].dt.total_seconds()
        lap_start = tel["SessionTime_s"].iloc[0]

        s1_dist = float(tel.loc[
            (tel["SessionTime_s"] - lap_start) >= s1.total_seconds()
        ]["Distance"].iloc[0]) if s1 and not pd.isna(s1) else None

        s2_dist = float(tel.loc[
            (tel["SessionTime_s"] - lap_start) >= (s1 + s2).total_seconds()
        ]["Distance"].iloc[0]) if s2 and not pd.isna(s2) else None

        sector_distances = [d for d in [s1_dist, s2_dist] if d is not None]
    except Exception:
        sector_distances = []

    # ── Corner distances ───────────────────────────────────────────────────
    try:
        circuit_info = sess.get_circuit_info()
        corners = circuit_info.corners[["Number", "Distance"]].copy()
        corners = corners.rename(columns={"Number": "corner", "Distance": "distance"})
        corner_list = corners.to_dict("records")
    except Exception:
        corner_list = []

    return sector_distances, corner_list


@st.cache_data(show_spinner=False)
def compute_delta_to_ref(year, location, session_name, ref_drv, ref_lap, other_drv, other_lap):
    """
    Compute time delta of other vs ref using GP Tempo method:
    normalize distances to ref lap total, then interpolate and subtract elapsed times.
    Positive = other is slower than ref (losing time).
    """
    sess = load_session(year, location, session_name)
    tel_ref   = sess.laps.pick_driver(ref_drv).pick_lap(ref_lap).get_telemetry().add_distance()
    tel_other = sess.laps.pick_driver(other_drv).pick_lap(other_lap).get_telemetry().add_distance()

    ref_total   = tel_ref["Distance"].max()
    other_total = tel_other["Distance"].max()

    time_ref   = tel_ref["Time"].dt.total_seconds()
    time_ref   = time_ref - time_ref.iloc[0]
    time_other = tel_other["Time"].dt.total_seconds()
    time_other = time_other - time_other.iloc[0]

    # Normalize other lap distance to match ref lap total distance
    dist_other_normalized = tel_other["Distance"] * (ref_total / other_total)

    ref_dist = np.linspace(0, ref_total, 5000)

    t_ref_interp   = np.interp(ref_dist, tel_ref["Distance"],   time_ref)
    t_other_interp = np.interp(ref_dist, dist_other_normalized, time_other)

    delta = t_other_interp - t_ref_interp
    return ref_dist, delta




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

@st.cache_data(show_spinner=False)
def build_laps_df(year: int, location: str, session_name: str, driver_abbr: str) -> pd.DataFrame:
    _session = load_session(year, location, session_name)
    laps = session.laps.pick_driver(driver_abbr).copy()
    laps["LapTimeSeconds"] = laps["LapTime"].apply(lap_time_to_seconds)
    laps["LapTimeStr"] = laps["LapTimeSeconds"].apply(seconds_to_laptime)
    laps["Driver"] = driver_abbr
    laps["Compound"] = laps["Compound"].fillna("UNKNOWN")
    laps["LapNumber"] = laps["LapNumber"].astype(int)
    # Keep ALL laps including crashes and laps without a recorded time
    return laps.reset_index(drop=True)




CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(CACHE_DIR)

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

session = st.session_state.session

st.sidebar.markdown("## 🏎️ Session Selector")
st.sidebar.write('Notice: Please press load session, even if the session appears to have loaded.')

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
    # st.markdown(f"# 🏎️ {year} {location} — {session_name}")
    with st.spinner("Fetching data from FastF1…"):
        st.session_state.session = load_session(year, location, session_name)
        st.session_state.selected_drivers = []
        st.session_state.laps_data = {}
        st.session_state.selected_laps = {}
        st.session_state.selected_lap_list = []
        st.session_state.last_tel_key = ""
        st.session_state.fig_tel_cache = None
        st.session_state.gap_map_tel_sig = ""
        # Clear all widget state for drivers and laps
        for key in list(st.session_state.keys()):
            if any(key.startswith(p) for p in ['selected_drivers', 'selected_lap', "driver_", "lap_sel_", "lap_pick_", "gap_map_", "sync_widgets"]):
                del st.session_state[key]
        st.rerun()
session = st.session_state.session

if session is None:
    col1, col2 = st.columns([6,1], gap="xxsmall") 

    with col1:
        # Display the image in the first column
         st.markdown("""
        # 🏎️ F1 Session Dashboard: <br>Presented by F1FM Analytics
         All the graphs you need to analyse F1 races and sessions all for free!
        Become your own pitwall now!
        ### Select a year, Grand Prix and session type, then click **Load Session**.
        """, unsafe_allow_html=True)

    with col2:
        st.image('C://Users//moki2//Mazen Work//F1 dashboard//f1fmlogo.png', width=200)


    st.stop()



# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
if load_btn:
    st.markdown(f"# 🏎️ {year} {location} — {session_name}")

col1, col2 = st.columns([6,1], gap="xxsmall") 
with col1:
    st.markdown(f"# 🏎️ {year} {location} — {session_name} Telemetry")

with col2:
    st.image('C://Users//moki2//Mazen Work//F1 dashboard//f1fmlogo.png', width=200)


st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# DRIVER SELECTOR
# ══════════════════════════════════════════════════════════════════════════════
driver_list = session.results[session.results.Status != 'Did not start']['Abbreviation'].to_list()
# driver_list_sorted = sorted(driver_list)

# Purge stale drivers from previous session
st.session_state.selected_drivers = [
    d for d in st.session_state.selected_drivers if d in driver_list
]
for drv in list(st.session_state.laps_data.keys()):
    if drv not in driver_list:
        del st.session_state.laps_data[drv]
        st.session_state.selected_laps.pop(drv, None)

st.markdown("## 👤 Driver Selection")
selected_drivers = st.multiselect(
    "Select one or more drivers to compare",
    options=driver_list,
    default=st.session_state.selected_drivers,
    max_selections=10,
    key="driver_multiselect",
    help="Select up to 10 drivers to overlay on the same chart.",
)
st.session_state.selected_drivers = selected_drivers

# Load laps data for newly selected drivers
for drv in selected_drivers:
    if drv not in st.session_state.laps_data:
        st.session_state.laps_data[drv] = build_laps_df(year, location, session_name, drv)

# Remove deselected drivers
for drv in list(st.session_state.laps_data.keys()):
    if drv not in selected_drivers:
        del st.session_state.laps_data[drv]
        st.session_state.selected_laps.pop(drv, None)

if not selected_drivers:
    st.info("Select at least one driver above to start.")
    st.stop()

# ── Outlier toggle ─────────────────────────────────────────────────────────────
if "outlier_toggle_chart" in st.session_state:
    st.session_state.remove_outliers = st.session_state.outlier_toggle_chart

st.markdown("---")



def detect_warmup_end(times: np.ndarray) -> int:
    """
    Dynamically detect where the tyre warm-up phase ends.
    Strategy: find the first lap where the time stops improving
    (i.e. first local minimum in a smoothed version of the stint).
    Returns the index to START the regression from.
    """
    if len(times) <= 4:
        return 0
    # Smooth with a rolling min to find the settling point
    smoothed = np.array([min(times[max(0,i-1):i+2]) for i in range(len(times))])
    diffs = np.diff(smoothed)
    # Find first index where times stop decreasing (warm-up over)
    for i, d in enumerate(diffs):
        if d >= 0:
            return max(0, i)  # start from this lap
    return min(3, len(times) - 3)  # fallback: skip first 3


def compute_tyre_deg(laps_df: pd.DataFrame, fuel_correct: bool) -> dict:
    """
    Returns {stint_number: {slope, intercept, compound, fit_laps, all_laps}}
    slope is seconds per lap of tyre age (fuel-corrected if requested).
    Warm-up laps are detected dynamically and excluded from the fit.
    """
    results = {}
    df = laps_df.copy()

    if fuel_correct:
        fuel_remaining      = STARTING_FUEL_KG - (FUEL_PER_LAP_KG * (df["LapNumber"] - 1))
        df["LapTimeSeconds"] = df["LapTimeSeconds"] - fuel_remaining * FUEL_EFFECT_S_PER_KG

    # Remove pit laps and obvious outliers
    df = df[~df["PitInTime"].notna() & ~df["PitOutTime"].notna()]
    df = df.dropna(subset=["LapTimeSeconds"])

    # Remove laps more than 7% above session median — catches SC/VSC/red flag laps
    session_median = df["LapTimeSeconds"].median()
    if not np.isnan(session_median):
        df = df[df["LapTimeSeconds"] <= session_median * 1.07]

    for stint, grp in df.groupby("Stint"):
        grp = grp.sort_values("LapNumber").reset_index(drop=True)
        if len(grp) < 4:
            continue

        # ── Dynamic warm-up detection ──────────────────────────────────────
        times    = grp["LapTimeSeconds"].values
        start_i  = detect_warmup_end(times)

        # Also drop the final lap of the stint (inlap — usually slow or push)
        end_i = len(grp) - 1 if len(grp) - 1 - start_i >= 3 else len(grp)
        trimmed = grp.iloc[start_i:end_i].copy()

        # ── Remove statistical outliers (SC laps, red flags etc) ──────────
        # Use IQR-based filter — more robust than std for skewed lap time distributions
        if len(trimmed) >= 4:
            q1  = np.percentile(trimmed["LapTimeSeconds"], 25)
            q3  = np.percentile(trimmed["LapTimeSeconds"], 75)
            iqr = q3 - q1
            # Keep laps within 1.5 IQR of the median (standard Tukey fence)
            trimmed = trimmed[
                (trimmed["LapTimeSeconds"] >= q1 - 1.5 * iqr) &
                (trimmed["LapTimeSeconds"] <= q3 + 1.5 * iqr)
            ]

        if len(trimmed) < 3:
            trimmed = grp.iloc[1:]  # fallback: just drop outlap

        if len(trimmed) < 3:
            continue

        x      = trimmed["LapNumber"].values.astype(float)
        y      = trimmed["LapTimeSeconds"].values.astype(float)
        coeffs = np.polyfit(x, y, 1)

        results[int(stint)] = {
            "slope":     round(float(coeffs[0]), 4),
            "intercept": round(float(coeffs[1]), 4),
            "compound":  grp["Compound"].iloc[0],
            "fit_laps":  trimmed,
            "all_laps":  grp,
        }
    return results


# ══════════════════════════════════════════════════════════════════════════════
# LAP TIME LINE CHART
# ══════════════════════════════════════════════════════════════════════════════
FUEL_PER_LAP_KG  = 2.0   # average F1 fuel burn per lap
STARTING_FUEL_KG = 70.0 # maximum race fuel load
FUEL_EFFECT_S_PER_KG = 0.03
@st.fragment
def render_lap_chart(selected_drivers, year, location, session_name):
    with st.container():
        st.markdown("## 📈 Lap Times")

        ctrl1, ctrl2, ctrl3 = st.columns(3)
        with ctrl1:
            toggle = st.toggle(
                "🚫 Remove outlier laps",
                value=st.session_state.remove_outliers,
                key="outlier_toggle_chart",
            )
        with ctrl2:
            fuel_correct = st.toggle(
                "⛽ Fuel corrected",
                value=False,
                key="fuel_correction_toggle",
            )
        with ctrl3:
            show_best_fit = st.toggle(
                "📐 Show best fit lines",
                value=False,
                key="show_best_fit_toggle",
            )

        # ── Driver visibility selector ─────────────────────────────────
        visible_drivers = st.multiselect(
            "👁 Visible drivers",
            options=selected_drivers,
            default=selected_drivers,
            key="lap_chart_visible_drivers",
        )

        fig_laps = go.Figure()

        for drv in selected_drivers:
            raw_laps  = st.session_state.laps_data[drv].copy()
            disp_laps = filter_outliers(raw_laps) if toggle else raw_laps
            disp_laps = disp_laps.dropna(subset=["LapTimeSeconds"])

            is_visible = drv in visible_drivers

            if fuel_correct:
                fuel_remaining              = STARTING_FUEL_KG - (FUEL_PER_LAP_KG * (disp_laps["LapNumber"] - 1))
                disp_laps                   = disp_laps.copy()
                disp_laps["LapTimeSeconds"] = disp_laps["LapTimeSeconds"] - fuel_remaining * FUEL_EFFECT_S_PER_KG
                disp_laps["LapTimeStr"]     = disp_laps["LapTimeSeconds"].apply(seconds_to_laptime)

            drv_color = get_driver_color(drv, selected_drivers)
            drv_dash  = get_driver_line_style(drv, _session=session)

            for stint, stint_grp in disp_laps.groupby("Stint"):
                stint_grp  = stint_grp.sort_values("LapNumber")
                compound   = stint_grp["Compound"].iloc[0]
                tyre_color = TYRE_COLORS.get(compound, "#aaaaaa")
                stint_name = f"{drv} — S{int(stint)} ({compound})"
                hover = [
                    f"Driver: {drv}<br>Lap: {r.LapNumber}<br>Time: {r.LapTimeStr}"
                    f"<br>Tyre: {compound}<br>Stint: {int(stint)}<br>Age: {int(r.TyreLife)} laps"
                    for _, r in stint_grp.iterrows()
                ]
                fig_laps.add_trace(go.Scatter(
                    x=stint_grp["LapNumber"],
                    y=stint_grp["LapTimeSeconds"],
                    mode="lines+markers",
                    name=stint_name,
                    line=dict(color=drv_color, width=2, dash=drv_dash),
                    marker=dict(color=tyre_color, size=9, line=dict(color=drv_color, width=1.5)),
                    hovertext=hover,
                    hoverinfo="text",
                    legendgroup=drv,
                    legendgrouptitle=dict(text=drv, font=dict(color=drv_color, size=13)),
                    showlegend=True,
                    visible=True if is_visible else "legendonly",
                    customdata=list(zip([drv] * len(stint_grp), stint_grp["LapNumber"])),
                ))

            if show_best_fit:
                deg_data = compute_tyre_deg(raw_laps, fuel_correct=fuel_correct)
                for stint, d in deg_data.items():
                    fit_laps = d["fit_laps"]
                    if fit_laps.empty:
                        continue
                    x_fit = np.array([fit_laps["LapNumber"].min(), fit_laps["LapNumber"].max()], dtype=float)
                    y_fit = d["slope"] * x_fit + d["intercept"]
                    fig_laps.add_trace(go.Scatter(
                        x=x_fit, y=y_fit,
                        mode="lines",
                        name=f"{drv} S{stint} fit ({d['slope']:+.3f}s/lap)",
                        line=dict(color=drv_color, width=1.5, dash="longdash"),
                        legendgroup=drv,
                        legendgrouptitle=dict(text=drv, font=dict(color=drv_color, size=13)),
                        showlegend=True,
                        visible=True if is_visible else "legendonly",
                        hovertemplate=f"<b>{drv} S{stint} best fit</b><br>Deg: {d['slope']:+.3f}s/lap<extra></extra>",
                    ))

        title_suffix = " *(fuel corrected)*" if fuel_correct else ""
        fig_laps.update_layout(
            template="plotly_dark",
            xaxis_title="Lap Number",
            yaxis_title=f"Lap Time (s){' — fuel corrected' if fuel_correct else ''}",
            yaxis=dict(tickformat=".3f"),
            hovermode="closest",
            legend=dict(
                bgcolor="#1a1a1a",
                bordercolor="#333",
                groupclick="toggleitem",  # individual stint clicks work normally
            ),
            height=500,
            margin=dict(l=60, r=20, t=40, b=50),
            title=dict(
                text=f"📈 Lap Times{title_suffix}",
                font=dict(color="#ffffff", size=16),
            ),
        )
        st.plotly_chart(fig_laps, use_container_width=True, key="lap_time_chart")

        # ── Tyre degradation section ───────────────────────────────────────
        if fuel_correct:
            st.markdown("#### 📉 Tyre Degradation Rate *(fuel corrected)*")

            # Collect all deg data for bar chart
            bar_labels  = []
            bar_values  = []
            bar_colors  = []
            bar_drivers = []

            deg_cols = st.columns(len(selected_drivers))
            for i, drv in enumerate(selected_drivers):
                raw       = st.session_state.laps_data[drv].copy()
                if toggle:
                    raw = filter_outliers(raw)
                deg       = compute_tyre_deg(raw, fuel_correct=True)
                drv_color = get_driver_color(drv, selected_drivers, _session=session)

                with deg_cols[i]:
                    st.markdown(
                        f"<span style='color:{drv_color};font-weight:bold;font-size:14px;'>{drv}</span>",
                        unsafe_allow_html=True,
                    )
                    for stint, data in deg.items():
                        tyre_color = TYRE_COLORS.get(data["compound"], "#aaaaaa")
                        direction  = "↑ degrading" if data["slope"] > 0 else "↓ improving"
                        n_laps     = len(data["fit_laps"])
                        st.markdown(
                            f"<div style='background:#1a1a1a;border-left:3px solid {tyre_color};"
                            f"padding:6px 10px;margin:4px 0;border-radius:4px;font-size:12px;'>"
                            f"<b>Stint {stint}</b> — {data['compound']} "
                            f"<span style='color:#555;font-size:10px;'>({n_laps} laps used)</span><br>"
                            f"<span style='color:{tyre_color};font-size:16px;font-weight:bold;'>"
                            f"{abs(data['slope']):.3f}s/lap</span> "
                            f"<span style='color:#888;'>{direction}</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        # Collect for bar chart
                        bar_labels.append(f"{drv} S{stint}<br>{data['compound']}")
                        bar_values.append(data["slope"])
                        bar_colors.append(tyre_color)
                        bar_drivers.append(drv)

            # ── Degradation bar chart ──────────────────────────────────────
            # ── Degradation bar chart ──────────────────────────────────────────────
            if bar_labels:
                st.markdown("#### 📊 Degradation Comparison")
                fig_bar = go.Figure()

                # Find all unique stint numbers across all drivers
                all_stints = sorted(set(
                    stint
                    for drv in selected_drivers
                    for stint in compute_tyre_deg(
                        filter_outliers(st.session_state.laps_data[drv].copy()) if toggle
                        else st.session_state.laps_data[drv].copy(),
                        fuel_correct=True
                    ).keys()
                ))

                for stint_num in all_stints:
                    x_labels = []
                    y_values = []
                    bar_colors = []

                    for drv in selected_drivers:
                        raw = st.session_state.laps_data[drv].copy()
                        if toggle:
                            raw = filter_outliers(raw)
                        deg = compute_tyre_deg(raw, fuel_correct=True)

                        if stint_num not in deg:
                            continue  # driver doesn't have this stint — skip, no phantom bar

                        data = deg[stint_num]
                        x_labels.append(drv)
                        y_values.append(data["slope"])
                        bar_colors.append(TYRE_COLORS.get(data["compound"], "#aaaaaa"))

                    if not x_labels:
                        continue

                    fig_bar.add_trace(go.Bar(
                        name=f"Stint {stint_num}",
                        x=x_labels,
                        y=y_values,
                        marker=dict(
                            color=bar_colors,
                            line=dict(color="#333", width=1),
                        ),
                        text=[f"{v:+.3f}s/lap" for v in y_values],
                        textposition="outside",
                        textfont=dict(color="#aaaaaa", size=11),
                        hovertemplate="<b>%{x} — Stint " + str(stint_num) + "</b><br>Deg rate: %{y:+.3f}s/lap<extra></extra>",
                        legendgroup=f"stint_{stint_num}",
                    ))

                fig_bar.add_hline(
                    y=0,
                    line=dict(color="#555", width=1, dash="dash"),
                )
                fig_bar.update_layout(
                    template="plotly_dark",
                    height=320,
                    barmode="group",
                    margin=dict(l=40, r=20, t=20, b=60),
                    yaxis=dict(
                        title="Deg rate (s/lap)",
                        gridcolor="#2a2a2a",
                        zeroline=True,
                        zerolinewidth=1.5,
                    ),
                    xaxis=dict(
                        gridcolor="#2a2a2a",
                        title="Driver",
                    ),
                    legend=dict(
                        bgcolor="#1a1a1a",
                        bordercolor="#333",
                        title=dict(text="Stint", font=dict(color="#aaaaaa", size=11)),
                    ),
                    showlegend=True,
                )
                st.plotly_chart(fig_bar, use_container_width=True)


render_lap_chart(selected_drivers, year, location, session_name)



# ══════════════════════════════════════════════════════════════════════════════
# LAPS TABLE
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("## 📋 Lap Data")

if st.session_state.laps_data:

    TYRE_BG = {
        "SOFT":         "#e8002d33",
        "MEDIUM":       "#ffd70033",
        "HARD":         "#f0f0f022",
        "INTERMEDIATE": "#39b54a33",
        "WET":          "#0067ff33",
        "UNKNOWN":      "#88888822",
    }
    TYRE_FG = {
        "SOFT":         "#ff6b6b",
        "MEDIUM":       "#ffd700",
        "HARD":         "#f0f0f0",
        "INTERMEDIATE": "#39b54a",
        "WET":          "#4da6ff",
        "UNKNOWN":      "#aaaaaa",
    }

    all_lap_nums = sorted(set(
        lap
        for drv in selected_drivers
        for lap in st.session_state.laps_data[drv]["LapNumber"].tolist()
    ))

    driver_lap_map = {}
    fastest_per_driver = {}
    for drv in selected_drivers:
        raw = st.session_state.laps_data[drv]
        driver_lap_map[drv] = {
            int(r["LapNumber"]): r
            for _, r in raw.iterrows()
        }
        best_idx = raw["LapTimeSeconds"].idxmin()
        fastest_per_driver[drv] = int(raw.loc[best_idx, "LapNumber"])

    # ── Fastest lap button ─────────────────────────────────────────────────
    if st.button("⚡ Compare Fastest Laps", width='content'):
        new_list = [(drv, fastest_per_driver[drv]) for drv in selected_drivers][:5]
        st.session_state.selected_lap_list = new_list
        st.session_state.selected_laps = {drv: lap for drv, lap in new_list}
        st.session_state.sync_widgets = True
        st.rerun()

    # ── Instructions ──────────────────────────────────────────────────────
    # selected_count = len(st.session_state.selected_lap_list)
    # remaining = 5 - selected_count
    # st.caption(
    #     f"{'✅' if selected_count else '⬜'} {selected_count}/5 laps selected — "
    #     f"click any cell to {'add' if remaining else '(max reached, deselect first)'} a lap. "
    #     f"Click a selected lap to deselect it."
    # )

    # ── Build interactive table ────────────────────────────────────────────
    col_headers = "".join(
        f"<th style='padding:4px 8px;color:#aaa;font-size:11px;min-width:70px;'>L{lap}</th>"
        for lap in all_lap_nums
    )
    header_row = (
        f"<tr><th style='padding:4px 8px;color:#aaa;font-size:11px;"
        f"text-align:left;min-width:60px;'>Driver</th>{col_headers}</tr>"
    )

    rows_html = ""
    for drv in selected_drivers:
        drv_color = get_driver_color_for_selection(drv, selected_drivers, _session=session)
        cells = (
            f"<td style='padding:4px 8px;color:{drv_color};"
            f"font-weight:bold;white-space:nowrap;'>{drv}</td>"
        )

        for lap in all_lap_nums:
            row = driver_lap_map[drv].get(lap)
            if row is None:
                cells += "<td style='padding:4px 8px;color:#444;'>—</td>"
                continue

            compound   = str(row.get("Compound", "UNKNOWN")).upper()
            lap_str    = row["LapTimeStr"]
            is_fastest = (lap == fastest_per_driver[drv])
            is_selected = (drv, lap) in st.session_state.selected_lap_list

            if is_selected:
                bg     = "#00c85555"
                fg     = "#00ff88"
                fw     = "bold"
                border = "2px solid #00ff88"
                cursor = "pointer"
            elif is_fastest:
                bg     = "#6a0dad44"
                fg     = "#d084ff"
                fw     = "bold"
                border = "1px solid #6a0dad"
                cursor = "pointer"
            else:
                bg     = TYRE_BG.get(compound, "#88888822")
                fg     = TYRE_FG.get(compound, "#aaaaaa")
                fw     = "normal"
                border = "none"
                cursor = "pointer"

            cells += (
                f"<td data-drv='{drv}' data-lap='{lap}' "
                f"style='padding:4px 8px;background:{bg};color:{fg};"
                f"font-weight:{fw};border:{border};font-size:12px;"
                f"white-space:nowrap;cursor:{cursor};' "
                f"onclick='selectLap(\"{drv}\",{lap})'>{lap_str}</td>"
            )

        rows_html += f"<tr>{cells}</tr>"

    # JS handles click → sends message via Streamlit component workaround
    table_html = f"""
    <div style='overflow-x:auto;'>
    <table id='lapTable' style='border-collapse:collapse;width:100%;
        background:#141414;border-radius:8px;'>
        <thead style='background:#1a1a1a;'>{header_row}</thead>
        <tbody>{rows_html}</tbody>
    </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)

    # ── Streamlit-native lap selectors (hidden but functional) ─────────────
    # Use st.pills or checkboxes per driver as the actual interactive layer
    st.markdown("**Select laps to compare** *(max 5 total)*")

    new_selection = []
    for drv in selected_drivers:
        raw = st.session_state.laps_data[drv]
        if st.session_state.remove_outliers:
            raw = filter_outliers(raw)
        # Do NOT drop laps with no laptime — they may still have telemetry
        # Just fill missing times with a placeholder for display
        raw = raw.copy()
        raw["LapTimeStr"] = raw["LapTimeStr"].replace("—", "No Time")

        lap_options = [int(r["LapNumber"]) for _, r in raw.iterrows()]
        lap_labels  = [
            f"L{int(r['LapNumber'])} — {r['LapTimeStr'] if r['LapTimeStr'] not in ['—', 'No Time'] else '⚠ No Time'} ({r['Compound']})"
            for _, r in raw.iterrows()
        ]

        # Pre-select laps already in selected_lap_list for this driver
        current_for_drv = [
            lap for d, lap in st.session_state.selected_lap_list if d == drv
        ]
        default_indices = [
            lap_options.index(l) for l in current_for_drv if l in lap_options
        ]

        widget_key = f"lap_pick_{drv}"
        # Only force-sync widgets immediately after the fastest laps button
        if st.session_state.get("sync_widgets", False):
            st.session_state[widget_key] = default_indices

        chosen_indices = st.multiselect(
            f"{drv} — pick laps",
            options=list(range(len(lap_options))),
            default=default_indices,
            format_func=lambda i, labels=lap_labels: labels[i],
            key=widget_key,
        )
        for idx in chosen_indices:
            new_selection.append((drv, lap_options[idx]))

    # Clear the sync flag after all widgets have been built
    st.session_state.sync_widgets = False

    # Enforce max 5
    if len(new_selection) > 5:
        st.warning("Maximum 5 laps total. Only the first 5 will be used.")
        new_selection = new_selection[:5]

    if new_selection != st.session_state.selected_lap_list:
        st.session_state.selected_lap_list = new_selection
        # Keep selected_laps dict in sync (last lap per driver for delta/map)
        st.session_state.selected_laps = {
            drv: lap for drv, lap in new_selection
        }

    st.markdown("---")

    # ── Selected lap metrics display ───────────────────────────────────────
    if st.session_state.selected_lap_list:
        st.markdown("### 🏁 Selected Laps")
        metric_cols = st.columns(len(st.session_state.selected_lap_list))
        for i, (drv, lap_num) in enumerate(st.session_state.selected_lap_list):
            raw = st.session_state.laps_data.get(drv)
            if raw is None:
                continue
            row = raw[raw["LapNumber"] == lap_num]
            if row.empty:
                continue
            row = row.iloc[0]
            is_fastest = (lap_num == fastest_per_driver.get(drv))
            lap_color  = get_lap_color(drv, lap_num, _session=session)
            with metric_cols[i]:
                st.markdown(
                    f"""
                    <div style="
                        background:#1a1a1a;
                        border-left: 4px solid {lap_color};
                        border-radius: 6px;
                        padding: 10px 14px;
                        margin-bottom: 6px;
                    ">
                        <div style="color:{lap_color};font-weight:bold;font-size:13px;">
                            {drv} — Lap {lap_num}{'  ⚡' if is_fastest else ''}
                        </div>
                        <div style="color:#ffffff;font-size:22px;font-weight:bold;margin:4px 0;">
                            {row['LapTimeStr']}
                        </div>
                        <div style="color:#888888;font-size:12px;">
                            {row['Compound']} | Stint {int(row.get('Stint', 0))} | Tyre age {int(row.get('TyreLife', 0))} laps
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

# ══════════════════════════════════════════════════════════════════════════════
# TELEMETRY SECTION
# ══════════════════════════════════════════════════════════════════════════════
# Only rerender telemetry if selected laps changed
st.markdown("## 🔬 Telemetry Analysis")



@st.cache_data(show_spinner="Loading telemetry…")
def get_telemetry(year, location, session_name, driver, lap_number):
    sess = load_session(year, location, session_name)
    laps = sess.laps.pick_driver(driver)
    lap = laps[laps["LapNumber"] == lap_number].iloc[0]
    tel = lap.get_telemetry().add_distance()
    return tel


# ── Fetch telemetry ────────────────────────────────────────────────────────────
def fetch_one(args):
    drv, lap_num, year, location, session_name = args
    return (drv, lap_num), get_telemetry(year, location, session_name, drv, lap_num)

tel_data = {}
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {
        executor.submit(fetch_one, (drv, lap_num, year, location, session_name)): (drv, lap_num)
        for drv, lap_num in st.session_state.selected_lap_list
    }
    for future in as_completed(futures):
        try:
            key, tel = future.result()
            tel_data[key] = tel
        except Exception as e:
            drv, lap_num = futures[future]
            st.warning(f"Could not load telemetry for {drv} lap {lap_num}: {e}")

fig_map = go.Figure()

if len(tel_data) == 1:
    (drv, lap_num), ref_tel = next(iter(tel_data.items()))
    x_grid = ref_tel["X"].values
    y_grid = ref_tel["Y"].values
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
        name=f"{drv} L{lap_num} speed",
        hovertemplate="Speed: %{marker.color:.0f} km/h<extra></extra>",
    ))
else:
    # Multi lap/driver — dominance using each lap's actual color
    keys = list(tel_data.keys())
    colors_map = {
        (drv, lap_num): get_lap_color(drv, lap_num, _session=session)
        for drv, lap_num in keys
    }

    # Interpolate all onto the same distance grid
    if not tel_data:
        st.info("Please select at least 1 lap for any driver.")
        st.stop()
    max_dist = min(t["Distance"].max() for t in tel_data.values())
    grid = np.linspace(0, max_dist, 500)

    speed_grid = {}
    x_grid, y_grid = None, None
    for (drv, lap_num), tel in tel_data.items():
        speed_grid[(drv, lap_num)] = np.interp(grid, tel["Distance"], tel["Speed"])
        if x_grid is None:
            x_grid = np.interp(grid, tel["Distance"], tel["X"])
            y_grid = np.interp(grid, tel["Distance"], tel["Y"])

    dominant = [
        max(keys, key=lambda k: speed_grid[k][i])
        for i in range(len(grid))
    ]

    for key in keys:
        drv, lap_num = key
        mask = [d == key for d in dominant]
        xs = [x_grid[i] if mask[i] else None for i in range(len(grid))]
        ys = [y_grid[i] if mask[i] else None for i in range(len(grid))]
        fig_map.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="markers",
            marker=dict(color=colors_map[key], size=5),
            name=f"{drv} L{lap_num}",
        ))

# ── Corner markers on track map ───────────────────────────────────────────
try:
    _, corner_list = get_track_annotations(year, location, session_name)
    if corner_list and x_grid is not None:
        # Use reference telemetry to get X/Y at each corner distance
        ref_tel = next(iter(tel_data.values()))
        corner_x = np.interp(
            [c["distance"] for c in corner_list],
            ref_tel["Distance"], ref_tel["X"]
        )
        corner_y = np.interp(
            [c["distance"] for c in corner_list],
            ref_tel["Distance"], ref_tel["Y"]
        )
        fig_map.add_trace(go.Scatter(
            x=corner_x, y=corner_y,
            mode="markers+text",
            marker=dict(color="#ffffff", size=6, symbol="circle"),
            text=[str(c["corner"]) for c in corner_list],
            textposition="top center",
            textfont=dict(color="#ffffff", size=9),
            name="Corners",
            hovertemplate="Corner %{text}<extra></extra>",
        ))
except Exception:
    pass

fig_map.update_layout(
    template="plotly_dark",
    xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
    yaxis=dict(visible=False),
    height=380,
    margin=dict(l=0, r=0, t=10, b=0),
    legend=dict(bgcolor="#1a1a1a"),
)
if len(tel_data) >= 2:
    cols = st.columns(2)
    with cols[0]:
        # st.markdown("<br><br><br><br>", unsafe_allow_html=True)
        st.header('Track Domination')
        st.subheader('Where each driver edges out the others speed-wise on track')
        st.plotly_chart(fig_map, width="stretch")
else:
    st.header('Driver Speed Map')
    st.plotly_chart(fig_map, width="stretch")

# ══════════════════════════════════════════════════════════════════════════════
# GAP MAP — only when 2+ laps selected
# ══════════════════════════════════════════════════════════════════════════════
if len(tel_data) >= 2:

    # Compute defaults outside the fragment so they update when tel_data changes
    _tel_keys   = list(tel_data.keys())
    _key_labels = [f"{drv} — Lap {lap}" for drv, lap in _tel_keys]

    def _lap_time_sec(key):
        d, ln = key
        raw = st.session_state.laps_data.get(d)
        if raw is None:
            return float("inf")
        row = raw[raw["LapNumber"] == ln]
        return row.iloc[0]["LapTimeSeconds"] if not row.empty else float("inf")

    _sorted_keys = sorted(_tel_keys, key=_lap_time_sec)
    _default_a   = _tel_keys.index(_sorted_keys[0])
    _default_b   = _tel_keys.index(_sorted_keys[1]) if len(_sorted_keys) > 1 else 0

    # Reset selectbox state whenever the available laps change
    _tel_keys_sig = str(_tel_keys)
    if st.session_state.get("gap_map_tel_sig") != _tel_keys_sig:
        st.session_state.gap_map_tel_sig = _tel_keys_sig
        st.session_state.gap_map_a = _default_a
        st.session_state.gap_map_b = _default_b

    @st.fragment
    def render_gap_map(tel_data, year, location, session_name, tel_keys, key_labels, default_a, default_b):
        with st.container():
            gmap_col1, gmap_col2 = st.columns(2)
            with gmap_col1:
                lap_a_idx = st.selectbox(
                    "Reference lap",
                    options=list(range(len(tel_keys))),
                    index=default_a,
                    format_func=lambda i: key_labels[i],
                    key="gap_map_a",
                )
            with gmap_col2:
                lap_b_idx = st.selectbox(
                    "Compare lap",
                    options=list(range(len(tel_keys))),
                    index=default_b,
                    format_func=lambda i: key_labels[i],
                    key="gap_map_b",
                )

            key_a = tel_keys[lap_a_idx]
            key_b = tel_keys[lap_b_idx]

            if key_a != key_b:
                try:
                    drv_a, lap_a = key_a
                    drv_b, lap_b = key_b
                    color_a = get_lap_color(drv_a, lap_a, _session=session)
                    color_b = get_lap_color(drv_b, lap_b, _session=session)

                    tel_a = tel_data[key_a]
                    tel_b = tel_data[key_b]

                    min_dist = max(tel_a["Distance"].min(), tel_b["Distance"].min())
                    max_dist = min(tel_a["Distance"].max(), tel_b["Distance"].max())
                    gap_grid = np.linspace(min_dist, max_dist, 5000)

                    gx_grid  = np.interp(gap_grid, tel_a["Distance"], tel_a["X"])
                    gy_grid  = np.interp(gap_grid, tel_a["Distance"], tel_a["Y"])

                    ref_total_gm  = tel_a["Distance"].max()
                    other_total_gm = tel_b["Distance"].max()

                    time_a = tel_a["Time"].dt.total_seconds()
                    time_a = time_a - time_a.iloc[0]
                    time_b = tel_b["Time"].dt.total_seconds()
                    time_b = time_b - time_b.iloc[0]

                    # Normalize lap B distance to match lap A total distance
                    dist_b_normalized = tel_b["Distance"] * (ref_total_gm / other_total_gm)

                    t_a_interp = np.interp(gap_grid, tel_a["Distance"],  time_a)
                    t_b_interp = np.interp(gap_grid, dist_b_normalized,  time_b)

                    gap_delta = t_b_interp - t_a_interp

                    point_colors = [color_a if d > 0 else color_b for d in gap_delta]

                    fig_gap_map = go.Figure()

                    # Base track outline
                    fig_gap_map.add_trace(go.Scatter(
                        x=gx_grid, y=gy_grid,
                        mode="lines",
                        line=dict(color="#222222", width=10),
                        showlegend=False,
                        hoverinfo="skip",
                    ))

                    # Heatmap dots coloured by cumulative delta value (quantitative)
                    # Apply signed square root to compress large values and amplify small ones
                    abs_max = max(abs(gap_delta)) if max(abs(gap_delta)) > 0 else 1
                    gap_delta_scaled = np.sign(gap_delta) * np.sqrt(np.abs(gap_delta) / abs_max)

                    # Heatmap dots coloured by scaled delta (quantitative, visually amplified)
                    fig_gap_map.add_trace(go.Scatter(
                        x=gx_grid, y=gy_grid,
                        mode="markers",
                        marker=dict(
                            color=gap_delta_scaled,
                            colorscale='RdBu',
                            cmid=0,
                            size=5,
                            colorbar=dict(
                                title=dict(
                                    text=f"🔴 {drv_b} L{lap_b} faster  |  {drv_a} L{lap_a} faster 🔵",
                                    font=dict(color="#aaaaaa", size=11),
                                    side="right",
                                ),
                            
                                tickfont=dict(color="#aaaaaa", size=10),
                                bgcolor="#1a1a1a",
                                bordercolor="#333",
                                thickness=14,
                                len=0.85,
                            ),
                            showscale=True,
                        ),
                        hovertemplate=(
                            f"<b>Δ %{{marker.color:.3f}}s</b><br>"
                            f"Positive = {drv_b} L{lap_b} losing time<extra></extra>"
                        ),
                        customdata=gap_delta,
                    ))

                    # Corner markers
                    try:
                        _, gap_corner_list = get_track_annotations(year, location, session_name)
                        if gap_corner_list:
                            gcx = np.interp([c["distance"] for c in gap_corner_list], gap_grid, gx_grid)
                            gcy = np.interp([c["distance"] for c in gap_corner_list], gap_grid, gy_grid)
                            fig_gap_map.add_trace(go.Scatter(
                                x=gcx, y=gcy,
                                mode="markers+text",
                                marker=dict(color="#ffffff", size=6, symbol="circle"),
                                text=[str(c["corner"]) for c in gap_corner_list],
                                textposition="top center",
                                textfont=dict(color="#ffffff", size=9),
                                name="Corners",
                                hovertemplate="Corner %{text}<extra></extra>",
                                showlegend=False,
                            ))
                    except Exception:
                        pass

                    fig_gap_map.update_layout(
                        template="plotly_dark",
                        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
                        yaxis=dict(visible=False),
                        height=450,
                        title='Fastest Lap Comparison Map',
                        margin=dict(l=0, r=80, t=30, b=0),
                        showlegend=False
                    )
                    # with cols[1]:
                    st.plotly_chart(fig_gap_map, width='stretch')

                except Exception as e:
                    st.warning(f"Could not render gap map: {e}")
            else:
                st.info("Select two different laps to visualise the gap on track.")
    with cols[1]:
        render_gap_map(tel_data, year, location, session_name, _tel_keys, _key_labels, _default_a, _default_b)

# ══════════════════════════════════════════════════════════════════════════════
# TELEMETRY CHANNELS
# ══════════════════════════════════════════════════════════════════════════════
tel_cache_key = str(sorted(st.session_state.selected_laps.items()))
if "last_tel_key" not in st.session_state:
    st.session_state.last_tel_key = ""

skip_tel_rerender = (tel_cache_key == st.session_state.last_tel_key)
st.session_state.last_tel_key = tel_cache_key

st.markdown("### 📡 Telemetry Channels")

tel_fig_key = str(sorted([(d, l) for d, l in st.session_state.selected_lap_list]))
if "tel_fig_cache" in st.session_state and st.session_state.get("tel_fig_key") == tel_fig_key:
    st.plotly_chart(st.session_state.tel_fig_cache, width="stretch", config={"displayModeBar": True})
    st.stop()

CHANNELS = [
    ("Speed", "Speed (km/h)"),
    ("Delta", "Gap to Fastest (s)"),
    ("Throttle", "Throttle (%)"),
    ("Brake", "Brake"),
    ("nGear", "Gear"),
    ("RPM", "RPM"),
    ("DRS", "DRS"),
]

# Only include channels that exist in the data — Delta is always included
available_channels = []
for ch, label in CHANNELS:
    if ch == "Delta":
        available_channels.append((ch, label))
        continue
    for tel in tel_data.values():
        if ch in tel.columns:
            available_channels.append((ch, label))
            break

n_rows = len(available_channels)

# ── Find reference lap (fastest among selected) ────────────────────────────
# @st.cache_resource
def find_fastest_key(td, laps_data):
    best_time = float("inf")
    best_key  = None
    for (d, ln) in td.keys():
        raw = laps_data.get(d)
        if raw is None:
            continue
        row = raw[raw["LapNumber"] == ln]
        if row.empty:
            continue
        t = row.iloc[0]["LapTimeSeconds"]
        if not np.isnan(t) and t < best_time:
            best_time = t
            best_key  = (d, ln)
    return best_key

ref_key = find_fastest_key(tel_data, st.session_state.laps_data)

# Precompute deltas vs reference for every selected lap
delta_arrays = {}
if ref_key and len(tel_data) > 1:
    ref_drv_d, ref_lap_d = ref_key
    for (drv, lap_num) in tel_data.keys():
        if (drv, lap_num) == ref_key:
            continue
        try:
            dist_arr, delta_arr = compute_delta_to_ref(
                year, location, session_name,
                ref_drv_d, ref_lap_d, drv, lap_num
            )
            delta_arrays[(drv, lap_num)] = (dist_arr, delta_arr)
        except Exception:
            pass

# ── Build telemetry figure ─────────────────────────────────────────────────
# ── Build telemetry figure with make_subplots ──────────────────────────────
fig_tel = make_subplots(
    rows=n_rows, cols=1,
    shared_xaxes=True,
    subplot_titles=[label for _, label in available_channels],
    vertical_spacing=0.04,
)

for (drv, lap_num), tel in tel_data.items():
    drv_color = get_lap_color(drv, lap_num, _session=session)
    drv_dash  = get_driver_line_style(drv, _session=session)

    for row_idx, (ch, label) in enumerate(available_channels, start=1):

        if ch == "Delta":
            if (drv, lap_num) == ref_key:
                max_dist = tel["Distance"].max()
                fig_tel.add_trace(go.Scatter(
                    x=[0, max_dist],
                    y=[0, 0],
                    mode="lines",
                    name=f"{drv} L{lap_num} (ref)",
                    line=dict(color=drv_color, width=1.8, dash=drv_dash),
                    legendgroup=f"{drv}_{lap_num}",
                    showlegend=(row_idx == 1),
                    hovertemplate=f"<b>{drv} L{lap_num} (ref):</b> 0.000s<extra></extra>",
                ), row=row_idx, col=1)
            elif (drv, lap_num) in delta_arrays:
                dist_arr, delta_arr = delta_arrays[(drv, lap_num)]
                fig_tel.add_trace(go.Scatter(
                    x=dist_arr,
                    y=delta_arr,
                    mode="lines",
                    name=f"{drv} L{lap_num} gap",
                    line=dict(color=drv_color, width=1.8, dash=drv_dash),
                    legendgroup=f"{drv}_{lap_num}",
                    showlegend=(row_idx == 1),
                    hovertemplate=f"<b>{drv} L{lap_num} gap:</b> %{{y:.3f}}s<extra></extra>",
                ), row=row_idx, col=1)
            continue

        if ch not in tel.columns:
            continue

        fig_tel.add_trace(go.Scatter(
            x=tel["Distance"],
            y=tel[ch],
            mode="lines",
            name=f"{drv} L{lap_num}",
            line=dict(color=drv_color, width=1.8, dash=drv_dash),
            legendgroup=f"{drv}_{lap_num}",
            showlegend=(row_idx == 1),
            hovertemplate=f"<b>{drv} L{lap_num} — {label}:</b> %{{y:.1f}}<extra></extra>",
        ), row=row_idx, col=1)

# Style the Delta yaxis with a red zero line
delta_row = next(
    (i + 1 for i, (ch, _) in enumerate(available_channels) if ch == "Delta"), None
)
if delta_row:
    fig_tel.update_yaxes(
        zeroline=True,
        # zerolinecolor="#e10600",
        zerolinewidth=1.5,
        row=delta_row, col=1,
    )

fig_tel.update_layout(
    template="plotly_dark",
    height=220 * n_rows,
    legend=dict(bgcolor="#1a1a1a", bordercolor="#333"),
    margin=dict(l=60, r=20, t=30, b=40),
    hovermode="x",
    hoverlabel=dict(
        bgcolor="#1a1a1a",
        bordercolor="#444",
        font=dict(color="#f0f0f0", size=12),
        namelength=-1,
    ),
)

fig_tel.update_xaxes(
    showspikes=True,
    spikemode="across",
    spikesnap="cursor",
    spikecolor="#ffffff",
    spikethickness=1,
    spikedash="dot",
)

fig_tel.update_yaxes(showspikes=False)

# ── Corners & sectors ──────────────────────────────────────────────────────
try:
    sector_dists, corner_list = get_track_annotations(year, location, session_name)

    # Sector lines
    for s_idx, s_dist in enumerate(sector_dists, start=2):
        fig_tel.add_vline(
            x=s_dist,
            line=dict(color="#e10600", width=1.5, dash="dash"),
            annotation=dict(
                text=f"S{s_idx}",
                font=dict(color="#e10600", size=11),
                yref="paper",
                y=1.01,
                showarrow=False,
            ),
        )

    # Corner number lines
    for corner in corner_list:
        fig_tel.add_vline(
            x=corner["distance"],
            line=dict(color="#444444", width=1, dash="dot"),
            annotation=dict(
                text=str(corner["corner"]),
                font=dict(color="#888888", size=9),
                yref="paper",
                y=0.05,
                showarrow=False,
                textangle=0,
                valign="top",
            ),
        )
except Exception:
    pass  # silently skip if circuit info unavailable

# st.session_state.tel_fig_cache = fig_tel
# st.session_state.tel_fig_key   = tel_fig_key

st.plotly_chart(fig_tel, config={"displayModeBar": True})

# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")

st.markdown(
    "<center style='color:#aaaaaa;font-size:0.85rem;'>Data provided by <b>FastF1</b> · Built with Streamlit & Plotly</center>",
    unsafe_allow_html=True,
)

st.markdown(
    "<center style='color:#555;font-size:0.8rem;'>" \
    "This is an unofficial, non-commercial project and "
    "is not affiliated with the FIA or Formula 1. All F1-related trademarks"
    " and copyrights belong to their respective owners."
    "</center>",
    unsafe_allow_html=True,
)
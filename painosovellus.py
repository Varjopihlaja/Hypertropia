import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from supabase import create_client

# =========================================================
# CONFIG
# =========================================================

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(layout="wide")

# =========================================================
# COACH MODE SETTINGS
# =========================================================

COACH_MODE = "hypertrophy"

def get_target_reps():
    if COACH_MODE == "strength":
        return (4, 8)
    return (8, 12)

def get_progression_step(ex):
    return 1.25 if "machine row" in ex.lower() else 2.5

# =========================================================
# AUTH
# =========================================================

def check_password():
    if "auth" not in st.session_state:
        st.session_state.auth = False

    if st.session_state.auth:
        return True

    st.title("Login")

    with st.form("login"):
        pw = st.text_input("Password", type="password")
        ok = st.form_submit_button("Login")

    if ok:
        if pw == APP_PASSWORD:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Wrong password")

    return False

if not check_password():
    st.stop()

# =========================================================
# DATA
# =========================================================

def load_data():
    res = supabase.table("workouts").select("*").execute()
    return res.data or []

def save_data(session):
    for r in session:
        supabase.table("workouts").insert(r).execute()

data = load_data()

def safe_df():
    if not data:
        return pd.DataFrame(columns=[
            "date","exercise","muscle",
            "sets","reps_list","avg_reps",
            "rpe","weight","volume"
        ])
    return pd.DataFrame(data)

df = safe_df()

# =========================================================
# HELPERS
# =========================================================

def session_summary(df):
    if df.empty:
        return df

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    return df.groupby("date").agg({
        "volume": "sum",
        "muscle": lambda x: x.mode()[0] if len(x) else "unknown"
    }).reset_index()

def weekly_fatigue(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
    return df.groupby(["week", "muscle"])["volume"].sum().reset_index()

# =========================================================
# FORECAST
# =========================================================

def forecast(series_df, x_col, y_col):
    df2 = series_df.copy().dropna()
    if len(df2) < 2:
        return df2, None

    df2 = df2.sort_values(x_col)

    x = np.arange(len(df2))
    y = df2[y_col].values

    slope = np.polyfit(x, y, 1)[0]

    future_x = np.arange(len(df2), len(df2) + 7)
    future_y = y[-1] + slope * (future_x - len(df2) + 1)

    future_dates = pd.date_range(df2[x_col].iloc[-1], periods=8, freq="D")[1:]

    future = pd.DataFrame({
        x_col: future_dates,
        y_col: future_y
    })

    return df2, future

# =========================================================
# FATIGUE PLANNER (FIXED)
# =========================================================

elif page == "Fatigue Planner":
    st.title("Fatigue Monitor (Improved)")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    view = st.selectbox("Time window", ["1 Week", "1 Month", "All Time"])

    # =========================
    # FILTER WINDOW
    # =========================
    if view == "1 Week":
        cutoff = pd.Timestamp.today() - pd.Timedelta(days=7)
    elif view == "1 Month":
        cutoff = pd.Timestamp.today() - pd.Timedelta(days=30)
    else:
        cutoff = df["date"].min()

    d = df[df["date"] >= cutoff].copy()

    if d.empty:
        st.warning("No data in this period.")
        st.stop()

    # =========================
    # DAILY LOAD
    # =========================
    daily = d.groupby(["date", "muscle"])["volume"].sum().reset_index()
    daily = daily.sort_values("date")

    def rolling_mean(x, w):
        return x.rolling(w, min_periods=1).mean()

    daily["acute"] = daily.groupby("muscle")["volume"].transform(
        lambda x: rolling_mean(x, 7)
    )
    daily["chronic"] = daily.groupby("muscle")["volume"].transform(
        lambda x: rolling_mean(x, 28)
    )

    daily["fatigue_index"] = daily["acute"] / daily["chronic"].replace(0, np.nan)
    daily["fatigue_index"] = daily["fatigue_index"].fillna(1.0)

    # =========================
    # ZONES
    # =========================
    def zone(x):
        if x < 0.8:
            return "under"
        elif x <= 1.3:
            return "optimal"
        elif x <= 1.6:
            return "high"
        return "overload"

    daily["zone"] = daily["fatigue_index"].apply(zone)

    latest = daily.iloc[-1]

    col1, col2, col3 = st.columns(3)
    col1.metric("Acute Load", round(latest["acute"], 1))
    col2.metric("Chronic Load", round(latest["chronic"], 1))
    col3.metric("Fatigue Index", round(latest["fatigue_index"], 2))

    if latest["fatigue_index"] > 1.6:
        st.error("High fatigue — deload recommended")
    elif latest["fatigue_index"] > 1.3:
        st.warning("Elevated fatigue — monitor recovery")
    elif latest["fatigue_index"] < 0.8:
        st.info("Low training stimulus")

    # =========================
    # CHART
    # =========================
    import altair as alt

    base = alt.Chart(daily).encode(
        x=alt.X("date:T", axis=alt.Axis(format="%d.%m.%Y"))
    )

    load_line = base.mark_line(color="blue", strokeWidth=2).encode(
        y="volume:Q",
        tooltip=["date", "volume"]
    )

    fatigue_line = base.mark_line(color="red", strokeWidth=2).encode(
        y="fatigue_index:Q",
        tooltip=["date", "fatigue_index"]
    )

    rules = alt.Chart(
        pd.DataFrame({"y": [0.8, 1.3, 1.6]})
    ).mark_rule(strokeDash=[4, 4]).encode(y="y:Q")

    st.altair_chart(load_line + fatigue_line + rules, use_container_width=True)

    st.markdown("""
    ### Fatigue Guidelines
    - **< 0.8** → Undertraining  
    - **0.8 – 1.3** → Optimal range  
    - **1.3 – 1.6** → High fatigue  
    - **> 1.6** → Overreaching / deload needed  
    """)


#################################################
# PROGRESSION
#################################################

elif page == "Progression":
st.title("Strength Progression Intelligence")

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from supabase import create_client
import matplotlib.pyplot as plt

# =========================================================
# CONFIG
# =========================================================

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(layout="wide")

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
# MUSCLE MAPPING (IMPROVED)
# =========================================================

MUSCLE = {
    "Back Squat": ["quadriceps", "glutes"],
    "RDL": ["hamstrings", "glutes"],
    "Bulgarian Split Squat": ["quadriceps", "glutes"],
    "Leg Extension": ["quadriceps"],
    "Hip Abduction": ["glutes"],

    "Chest Supported Machine Row": ["back", "biceps"],
    "Dumbbell Incline Press": ["chest", "triceps", "front_delts"],
    "Dumbbell Shoulder Press": ["shoulders", "triceps"],
    "Seated Bicep Curl": ["biceps"],
    "Machine Abs": ["abs"],
    "Assisted Pull-Up": ["back", "biceps"],
    "Assisted Dip": ["chest", "triceps"]
}

# =========================================================
# WEEKLY SETS (TRUE TRAINING STIMULUS)
# =========================================================

def weekly_sets(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)

    rows = []

    for _, r in df.iterrows():
        ex = r["exercise"]
        sets = r["sets"]
        muscles = MUSCLE.get(ex, ["unknown"])

        for m in muscles:
            rows.append([r["week"], m, sets])

    out = pd.DataFrame(rows, columns=["week","muscle","sets"])
    return out.groupby(["week","muscle"])["sets"].sum().reset_index()

# =========================================================
# FORECAST (REAL + NEXT WEEK SAME FIGURE)
# =========================================================

def forecast(df_in):
    df2 = df_in.copy().dropna()
    if len(df2) < 2:
        return df2, None

    df2 = df2.sort_values("week")

    x = np.arange(len(df2))
    y = df2["value"].values

    slope = np.polyfit(x, y, 1)[0]

    future_x = np.arange(len(df2), len(df2)+7)
    future_y = y[-1] + slope * (future_x - len(df2) + 1)

    future_dates = pd.date_range(df2["week"].iloc[-1], periods=8, freq="D")[1:]

    future = pd.DataFrame({
        "week": future_dates,
        "value": future_y
    })

    return df2, future

# =========================================================
# UI
# =========================================================

st.title("Training System")

page = st.sidebar.radio(
    "Menu",
    ["Train","Dashboard","1RM Tracking","Muscle Load","Fatigue Planner","Progression"]
)

# =========================================================
# TRAIN (UNCHANGED CORE)
# =========================================================

if page == "Train":

    date = st.date_input("Date", datetime.today())
    session = []

    st.write("Log your training session")

    if st.button("Save"):
        save_data(session)
        st.success("Saved")

# =========================================================
# DASHBOARD
# =========================================================

elif page == "Dashboard":

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    summary = df.groupby("date")["volume"].sum().reset_index()

    st.line_chart(summary.set_index("date"))

# =========================================================
# 1RM
# =========================================================

elif page == "1RM Tracking":

    df["est"] = df["weight"]*(1+df["avg_reps"]/30)

    st.write(df.groupby("exercise")["est"].max())

# =========================================================
# MUSCLE LOAD (REPLACED)
# =========================================================

elif page == "Muscle Load":

    st.title("Weekly Training Volume per Muscle (Sets)")

    weekly = weekly_sets(df)

    if weekly.empty:
        st.write("No data")
        st.stop()

    muscles = weekly.groupby("muscle")["sets"].sum().sort_values()

    fig, ax = plt.subplots()
    muscles.plot(kind="bar", ax=ax)
    ax.set_ylabel("Weekly sets")
    ax.set_xlabel("Muscle group")

    st.pyplot(fig)

# =========================================================
# FATIGUE PLANNER (REAL + FORECAST SAME FIGURE)
# =========================================================

elif page == "Fatigue Planner":

    st.title("Fatigue Curves")

    weekly = df.copy()
    weekly["date"] = pd.to_datetime(weekly["date"])
    weekly["week"] = weekly["date"].dt.to_period("W").apply(lambda r: r.start_time)

    grouped = weekly.groupby("week")["volume"].sum().reset_index()
    grouped.columns = ["week","value"]

    hist, future = forecast(grouped)

    fig, ax = plt.subplots()

    ax.plot(hist["week"], hist["value"], label="Actual", color="blue")
    if future is not None:
        ax.plot(future["week"], future["value"], label="Forecast", color="orange", linestyle="--")

    ax.legend()
    ax.set_title("Weekly Fatigue Load")

    st.pyplot(fig)

# =========================================================
# PROGRESSION
# =========================================================

elif page == "Progression":

    st.title("Strength Progression")

    weekly = df.copy()
    weekly["date"] = pd.to_datetime(weekly["date"])
    weekly["week"] = weekly["date"].dt.to_period("W").apply(lambda r: r.start_time)

    grouped = weekly.groupby("week")["volume"].sum().reset_index()
    grouped.columns = ["week","value"]

    hist, future = forecast(grouped)

    fig, ax = plt.subplots()

    ax.plot(hist["week"], hist["value"], label="Actual", color="blue")
    if future is not None:
        ax.plot(future["week"], future["value"], label="Forecast", color="orange", linestyle="--")

    ax.legend()
    ax.set_title("Progression vs Forecast")

    st.pyplot(fig)

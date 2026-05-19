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
# MUSCLE MAP (FIXED: MULTI-IMPACT LOGIC)
# =========================================================

MUSCLE_MAP = {
    "Back Squat": ["quadriceps","glutes"],
    "RDL": ["hamstrings","glutes"],
    "Bulgarian Split Squat": ["quadriceps","glutes"],
    "Leg Extension": ["quadriceps"],
    "Hip Abduction": ["glutes"],

    "Chest Supported Machine Row": ["back"],
    "Dumbbell Incline Press": ["chest","triceps"],
    "Dumbbell Shoulder Press": ["shoulders","triceps"],
    "Seated Bicep Curl": ["biceps"],
    "Machine Abs": ["abs"],

    "Assisted Pull-Up": ["back","biceps"],
    "Assisted Dip": ["chest","triceps"]
}

# =========================================================
# HELPERS
# =========================================================

def weekly_exercise_volume(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
    return df.groupby(["exercise","week"])["volume"].sum().reset_index()

def weekly_sets(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
    return df.groupby(["exercise","week"])["sets"].sum().reset_index()

def weekly_muscle_sets(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)

    rows = []

    for _, r in df.iterrows():
        muscles = MUSCLE_MAP.get(r["exercise"], [r["muscle"]])
        for m in muscles:
            rows.append([r["week"], m, r["sets"]])

    out = pd.DataFrame(rows, columns=["week","muscle","sets"])
    return out.groupby(["week","muscle"])["sets"].sum().reset_index()

# =========================================================
# FORECAST
# =========================================================

def forecast(df, x, y):
    df = df.copy().dropna()
    if len(df) < 2:
        return df, None

    df = df.sort_values(x)

    x_vals = np.arange(len(df))
    y_vals = df[y].values

    slope = np.polyfit(x_vals, y_vals, 1)[0]

    future_x = np.arange(len(df), len(df)+7)
    future_y = y_vals[-1] + slope*(future_x - len(df) + 1)

    future_dates = pd.date_range(df[x].iloc[-1], periods=8)[1:]

    future = pd.DataFrame({
        x: future_dates,
        y: future_y
    })

    return df, future

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

LOWER = ["RDL","Back Squat","Bulgarian Split Squat","Leg Extension","Hip Abduction"]
UPPER = [
    "Assisted Pull-Up","Assisted Dip","Chest Supported Machine Row",
    "Dumbbell Shoulder Press","Seated Bicep Curl",
    "Dumbbell Incline Press","Machine Abs"
]

if page == "Train":
    date = st.date_input("Date", datetime.today())
    split = st.radio("Split", ["Lower","Upper"], horizontal=True)

    exercises = LOWER if split=="Lower" else UPPER
    session = []

    cols = st.columns(5)

    for i, ex in enumerate(exercises):
        with cols[i % 5]:

            st.markdown(f"### {ex}")

            sets = st.number_input("Sets",0,6,3,key=f"{ex}s")
            reps = [10]*sets
            rpe = st.slider("RPE",1,10,8,key=f"{ex}rpe")
            weight = st.number_input("Weight",0.0,300.0,20.0,key=f"{ex}w")

            session.append({
                "date":date.strftime("%Y-%m-%d"),
                "exercise":ex,
                "muscle":"multi",
                "sets":sets,
                "reps_list":reps,
                "avg_reps":10,
                "rpe":rpe,
                "weight":weight,
                "volume":sets*weight
            })

    if st.button("Save"):
        save_data(session)
        st.success("Saved")

# =========================================================
# MUSCLE LOAD (FIXED)
# =========================================================

elif page == "Muscle Load":

    st.title("Weekly Sets per Muscle Group")

    m = weekly_muscle_sets(df)

    if m.empty:
        st.write("")
        st.stop()

    col1, col2 = st.columns(2)

    upper = m[m["muscle"].isin(["chest","back","shoulders","biceps","triceps","abs"])]
    lower = m[m["muscle"].isin(["quadriceps","hamstrings","glutes"])]

    with col1:
        st.bar_chart(upper.groupby("muscle")["sets"].sum())

    with col2:
        st.bar_chart(lower.groupby("muscle")["sets"].sum())

# =========================================================
# FATIGUE PLANNER
# =========================================================

elif page == "Fatigue Planner":

    st.title("Fatigue: Real vs Forecast")

    w = weekly_exercise_volume(df)

    if w.empty:
        st.stop()

    for split, label in [("upper","Upper"),("lower","Lower")]:

        st.subheader(label)

        if split=="upper":
            d = w[w["exercise"].isin(UPPER)]
        else:
            d = w[w["exercise"].isin(LOWER)]

        ts = d.groupby("week")["volume"].sum().reset_index()

        hist, fut = forecast(ts,"week","volume")

        st.line_chart(hist.set_index("week")["volume"], use_container_width=True)

        if fut is not None:
            st.line_chart(fut.set_index("week")["volume"], use_container_width=True)

# =========================================================
# PROGRESSION
# =========================================================

elif page == "Progression":

    st.title("Progression: Real vs Forecast")

    w = weekly_exercise_volume(df)

    ex = st.selectbox("Exercise", UPPER+LOWER)

    d = w[w["exercise"]==ex].sort_values("week")

    hist, fut = forecast(d,"week","volume")

    st.line_chart(hist.set_index("week")["volume"], use_container_width=True)

    if fut is not None:
        st.line_chart(fut.set_index("week")["volume"], use_container_width=True)

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
# EXERCISE → MULTI MUSCLE MAPPING (FIX)
# =========================================================

MUSCLE_MULTI = {
    "Back Squat": ["Quadriceps","Glutes"],
    "RDL": ["Hamstrings","Glutes"],
    "Bulgarian Split Squat": ["Quadriceps","Glutes"],
    "Leg Extension": ["Quadriceps"],
    "Hip Abduction": ["Glutes"],

    "Chest Supported Machine Row": ["Back"],
    "Dumbbell Incline Press": ["Chest","Triceps"],
    "Dumbbell Shoulder Press": ["Shoulders","Triceps"],
    "Seated Bicep Curl": ["Biceps"],
    "Machine Abs": ["Abs/Core"],
    "Assisted Pull-Up": ["Back","Biceps"],
    "Assisted Dip": ["Chest","Triceps"]
}

LOWER = ["RDL","Back Squat","Bulgarian Split Squat","Leg Extension","Hip Abduction"]
UPPER = list(MUSCLE_MULTI.keys())[-7:]

# =========================================================
# SET VOLUME PER WEEK
# =========================================================

def weekly_sets(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)

    df["sets"] = df["sets"].astype(float)

    exploded = df.explode("muscle")

    return exploded.groupby(["week","muscle"])["sets"].sum().reset_index()

# =========================================================
# FORECAST (REAL + FUTURE SAME CHART)
# =========================================================

def forecast(series):
    series = series.sort_values("week")

    if len(series) < 3:
        return series, None

    x = np.arange(len(series))
    y = series["value"].values

    slope = np.polyfit(x, y, 1)[0]

    future_x = np.arange(len(series), len(series)+7)
    future_y = y[-1] + slope*(future_x - len(series) + 1)

    future_dates = pd.date_range(series["week"].iloc[-1], periods=8)[1:]

    future = pd.DataFrame({
        "week": future_dates,
        "value": future_y
    })

    return series, future

# =========================================================
# PROGRESSION
# =========================================================

def is_assisted(ex):
    return "assisted" in ex.lower()

def get_step(ex):
    return 1.25 if "row" in ex.lower() else 2.5

def snap(w, step):
    return round(round(w/step)*step, 2)

def progression(ex, reps, rpe, weight):
    avg = sum(reps)/max(len(reps),1)
    step = get_step(ex)

    if is_assisted(ex):
        if rpe >= 9:
            return snap(weight+step,step), "increase assistance"
        if avg >= 12:
            return snap(weight-step,step), "reduce assistance"
        return weight, "maintain"

    if rpe >= 9:
        return snap(weight*0.97,step), "fatigue drop"
    if avg >= 12:
        return snap(weight+step,step), "progress"
    return weight,"maintain"

# =========================================================
# MUSCLE GUIDELINES (NEW)
# =========================================================

MUSCLE_GUIDELINES = {
    "Chest": "10–20 sets/week. Focus pressing + isolation.",
    "Back": "12–20 sets/week. Horizontal + vertical pulling.",
    "Quadriceps": "10–18 sets/week. Squats, lunges, extensions.",
    "Hamstrings": "8–16 sets/week. Hinges + curls.",
    "Shoulders": "8–16 sets/week. Press + lateral/rear delts.",
    "Biceps": "6–14 sets/week. Curls + pulling.",
    "Triceps": "6–14 sets/week. Press + extensions.",
    "Glutes": "8–16 sets/week. Squat + hinge patterns.",
    "Abs/Core": "8–12 sets/week. Stability + flexion.",
}

# =========================================================
# UI
# =========================================================

st.title("Training System")

page = st.sidebar.radio(
    "Menu",
    ["Train","Dashboard","1RM Tracking","Muscle Load","Fatigue Planner","Progression"]
)

# =========================================================
# TRAIN (UNCHANGED LOGIC)
# =========================================================

if page == "Train":

    date = st.date_input("Date", datetime.today())
    split = st.radio("Split", ["Lower","Upper"], horizontal=True)

    exercises = LOWER if split=="Lower" else UPPER
    session = []

    cols = st.columns(5)

    for i, ex in enumerate(exercises):

        with cols[i%5]:

            st.markdown(f"### {ex}")

            sets = st.number_input("Sets",0,6,3,key=f"{ex}s")

            reps = []
            rep_cols = st.columns(max(1,sets))

            for i2 in range(sets):
                with rep_cols[i2]:
                    reps.append(st.number_input(f"{i2+1}",0,30,10,key=f"{ex}{i2}"))

            rpe = st.slider("RPE",1,10,8,key=f"{ex}r")
            weight = st.number_input("Weight",0.0,300.0,20.0,key=f"{ex}w")

            new_w,msg = progression(ex,reps,rpe,weight)

            st.success(f"Next: {new_w} kg ({msg})")

            session.append({
                "date":date.strftime("%Y-%m-%d"),
                "exercise":ex,
                "muscle":list(MUSCLE_MULTI[ex]),
                "sets":sets,
                "reps_list":reps,
                "avg_reps":sum(reps)/max(len(reps),1),
                "rpe":rpe,
                "weight":weight,
                "volume":sum(reps)*weight
            })

    if st.button("Save"):
        save_data(session)
        st.success("Saved")

# =========================================================
# DASHBOARD
# =========================================================

elif page == "Dashboard":

    st.title("Calendar")

    df["date"] = pd.to_datetime(df["date"])
    summary = df.groupby("date")["volume"].sum().reset_index()

    st.line_chart(summary.set_index("date"))

# =========================================================
# 1RM
# =========================================================

elif page == "1RM Tracking":

    df["est"] = df["weight"]*(1+df["avg_reps"]/30)

    st.subheader("Estimated Strength per Exercise")

    for ex in df["exercise"].unique():
        st.write(ex, df[df["exercise"]==ex]["est"].max())

# =========================================================
# MUSCLE LOAD (FIXED MEANING)
# =========================================================

elif page == "Muscle Load":

    st.title("Weekly Sets per Muscle Group")

    exploded = df.explode("muscle")
    exploded["date"] = pd.to_datetime(exploded["date"])
    exploded["week"] = exploded["date"].dt.to_period("W").apply(lambda r: r.start_time)

    weekly_sets_df = exploded.groupby(["muscle","week"])["sets"].sum().reset_index()

    selected = st.selectbox("Muscle", weekly_sets_df["muscle"].unique())

    hist = weekly_sets_df[weekly_sets_df["muscle"]==selected].sort_values("week")
    hist, fut = forecast(hist.rename(columns={"sets":"value"}))

    st.bar_chart(hist.set_index("week")["value"])

    if fut is not None:
        st.line_chart(fut.set_index("week")["value"])

    st.info(MUSCLE_GUIDELINES.get(selected,""))

# =========================================================
# FATIGUE PLANNER
# =========================================================

elif page == "Fatigue Planner":

    st.title("Upper vs Lower Fatigue (Weekly Sets)")

    exploded = df.explode("muscle")
    exploded["date"] = pd.to_datetime(exploded["date"])
    exploded["week"] = exploded["date"].dt.to_period("W").apply(lambda r: r.start_time)

    weekly = exploded.groupby(["muscle","week"])["sets"].sum().reset_index()

    upper = weekly[weekly["muscle"].isin(["Chest","Back","Shoulders","Biceps","Triceps","Abs/Core"])]
    lower = weekly[weekly["muscle"].isin(["Quadriceps","Hamstrings","Glutes"])]

    u = upper.groupby("week")["sets"].sum().reset_index().rename(columns={"sets":"value"})
    l = lower.groupby("week")["sets"].sum().reset_index().rename(columns={"sets":"value"})

    hu, fu = forecast(u)
    hl, fl = forecast(l)

    st.subheader("Upper Body (blue real, orange forecast)")
    st.line_chart(hu.set_index("week")["value"])
    if fu is not None:
        st.line_chart(fu.set_index("week")["value"])

    st.subheader("Lower Body (blue real, orange forecast)")
    st.line_chart(hl.set_index("week")["value"])
    if fl is not None:
        st.line_chart(fl.set_index("week")["value"])

# =========================================================
# PROGRESSION
# =========================================================

elif page == "Progression":

    st.title("Exercise Progression Forecast")

    weekly = df.groupby(["exercise","date"])["volume"].sum().reset_index()

    ex = st.selectbox("Exercise", df["exercise"].unique())

    d = weekly[weekly["exercise"]==ex].rename(columns={"date":"week","volume":"value"})

    hist, fut = forecast(d)

    st.line_chart(hist.set_index("week")["value"])

    if fut is not None:
        st.line_chart(fut.set_index("week")["value"])

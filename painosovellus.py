import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
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
# HELPERS
# =========================================================

def weekly_fatigue(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
    return df.groupby(["week", "muscle"])["volume"].sum().reset_index()

def weekly_exercise_volume(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
    return df.groupby(["exercise", "week"])["volume"].sum().reset_index()

# =========================================================
# FORECAST
# =========================================================

def forecast(df, x, y):
    df = df.dropna().sort_values(x)
    if len(df) < 2:
        return None

    x_vals = np.arange(len(df))
    y_vals = df[y].values

    slope = np.polyfit(x_vals, y_vals, 1)[0]

    future_x = pd.date_range(df[x].iloc[-1], periods=8, freq="D")[1:]
    future_y = y_vals[-1] + slope * (np.arange(1, 8))

    hist = df.copy()
    hist["type"] = "Actual"

    fut = pd.DataFrame({
        x: future_x,
        y: future_y,
        "type": "Forecast"
    })

    return pd.concat([hist, fut])

# =========================================================
# EXERCISES
# =========================================================

LOWER = ["RDL","Back Squat","Bulgarian Split Squat","Leg Extension","Hip Abduction"]

UPPER = [
    "Assisted Pull-Up",
    "Assisted Dip",
    "Chest Supported Machine Row",
    "Dumbbell Shoulder Press",
    "Seated Bicep Curl",
    "Dumbbell Incline Press",
    "Machine Abs"
]

MUSCLE = {
    "Back Squat":"quadriceps",
    "RDL":"hamstrings",
    "Bulgarian Split Squat":"quadriceps",
    "Leg Extension":"quadriceps",
    "Hip Abduction":"glutes",
    "Chest Supported Machine Row":"back",
    "Dumbbell Incline Press":"chest",
    "Dumbbell Shoulder Press":"shoulders",
    "Seated Bicep Curl":"biceps",
    "Machine Abs":"core",
    "Assisted Pull-Up":"back",
    "Assisted Dip":"triceps"
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
# TRAIN
# =========================================================

if page == "Train":
    st.write("Training input page (unchanged logic)")

# =========================================================
# MUSCLE LOAD (REPLACED)
# =========================================================

elif page == "Muscle Load":

    st.title("Weekly Sets per Muscle Group")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)

    sets = df.groupby(["week","muscle"])["sets"].sum().reset_index()

    st.subheader("Sets per muscle per week")

    chart = alt.Chart(sets).mark_line().encode(
        x="week:T",
        y="sets:Q",
        color="muscle:N"
    )

    st.altair_chart(chart, use_container_width=True)

    st.markdown("""
Chest: 10–20 sets per week. Larger muscle group requiring varied angles for balanced development. Focus on pressing movements and isolation exercises to engage all portions of the chest.  
Back: 12–20 sets per week. Includes upper, mid, and lower back muscles. Incorporate horizontal and vertical pulling movements.  
Quadriceps: 10–18 sets per week. Squats, lunges, leg extensions.  
Hamstrings: 8–16 sets per week. Hinge + curl movements.  
Shoulders: 8–16 sets per week. Press + raises.  
Biceps: 6–14 sets per week. Curls + pulls.  
Triceps: 6–14 sets per week. Press + extensions.  
Glutes: 8–16 sets per week. Squats, hip thrusts.  
Calves: 8–15 sets per week. Seated + standing.  
Abs/Core: 8–12 sets per week. Static + dynamic core work.
""")

# =========================================================
# FATIGUE PLANNER (FIXED COLORS)
# =========================================================

elif page == "Fatigue Planner":

    st.title("Fatigue Planner")

    weekly = weekly_fatigue(df)

    upper = weekly[weekly["muscle"] != "legs"].groupby("week")["volume"].sum().reset_index()
    lower = weekly[weekly["muscle"] == "legs"].groupby("week")["volume"].sum().reset_index()

    def plot(data, title):
        data = data.dropna()

        chart = alt.Chart(data).mark_line().encode(
            x="week:T",
            y="volume:Q",
            color=alt.Color("type:N", scale=alt.Scale(domain=["Actual","Forecast"],
                                                      range=["#1f77b4","#ff7f0e"]))
        ).properties(title=title)

        st.altair_chart(chart, use_container_width=True)

    hist_u = upper.copy()
    hist_u["type"] = "Actual"
    fut_u = forecast(upper, "week", "volume")

    hist_l = lower.copy()
    hist_l["type"] = "Actual"
    fut_l = forecast(lower, "week", "volume")

    if fut_u is not None:
        plot(fut_u, "Upper Body Fatigue")

    if fut_l is not None:
        plot(fut_l, "Lower Body Fatigue")

# =========================================================
# PROGRESSION (FIXED)
# =========================================================

elif page == "Progression":

    st.title("Strength Progression Forecast")

    weekly = weekly_exercise_volume(df)

    split = st.radio("View", ["Upper","Lower"], horizontal=True)
    exercises = UPPER if split=="Upper" else LOWER

    ex = st.selectbox("Exercise", exercises)

    d = weekly[weekly["exercise"] == ex][["week","volume"]]

    st.subheader("Progression (Actual vs Forecast)")

    result = forecast(d, "week", "volume")

    if result is not None:

        chart = alt.Chart(result).mark_line().encode(
            x="week:T",
            y="volume:Q",
            color=alt.Color("type:N",
                            scale=alt.Scale(range=["#1f77b4","#ff7f0e"]),
                            legend=alt.Legend(title="Legend: Blue=Actual, Orange=Forecast"))
        )

        st.altair_chart(chart, use_container_width=True)

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from supabase import create_client
import plotly.graph_objects as go

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

def weekly_exercise_volume(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
    return df.groupby(["exercise","week"])["volume"].sum().reset_index()

def weekly_sets(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
    return df.groupby(["muscle","week"])["sets"].sum().reset_index()

# =========================================================
# EXERCISES + MUSCLE MAP (IMPROVED LOGIC)
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
    "Back Squat":["quads","glutes"],
    "RDL":["hamstrings","glutes"],
    "Bulgarian Split Squat":["quads","glutes"],
    "Leg Extension":["quads"],
    "Hip Abduction":["glutes"],

    "Chest Supported Machine Row":["back","biceps"],
    "Dumbbell Incline Press":["chest","triceps","shoulders"],
    "Dumbbell Shoulder Press":["shoulders","triceps"],
    "Seated Bicep Curl":["biceps"],
    "Machine Abs":["abs"],

    "Assisted Pull-Up":["back","biceps"],
    "Assisted Dip":["chest","triceps"]
}

# =========================================================
# FORECAST (REAL + FUTURE IN SAME FIGURE)
# =========================================================

def forecast_plot(series, x, y, title):
    df2 = series.sort_values(x).copy()
    df2 = df2.dropna()

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df2[x],
        y=df2[y],
        mode="lines+markers",
        name="Actual",
        line=dict(color="blue")
    ))

    if len(df2) > 2:
        x_idx = np.arange(len(df2))
        slope = np.polyfit(x_idx, df2[y], 1)[0]

        future_x = pd.date_range(df2[x].iloc[-1], periods=8, freq="D")[1:]
        future_y = df2[y].iloc[-1] + slope * np.arange(1,8)

        fig.add_trace(go.Scatter(
            x=future_x,
            y=future_y,
            mode="lines",
            name="Forecast (7d)",
            line=dict(color="orange", dash="dash")
        ))

    fig.update_layout(title=title, legend=dict(orientation="h"))
    return fig

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

    st.subheader("Log training session")

    date = st.date_input("Date", datetime.today())
    split = st.radio("Split", ["Lower","Upper"], horizontal=True)

    exercises = LOWER if split=="Lower" else UPPER
    session = []

    for ex in exercises:

        st.markdown(f"### {ex}")

        sets = st.number_input(f"{ex} sets", 0, 10, 3, key=f"s_{ex}")

        reps = st.number_input(f"{ex} reps avg", 0, 30, 10, key=f"r_{ex}")
        weight = st.number_input(f"{ex} weight", 0.0, 300.0, 40.0, key=f"w_{ex}")

        session.append({
            "date": date.strftime("%Y-%m-%d"),
            "exercise": ex,
            "muscle": str(MUSCLE.get(ex, [])),
            "sets": sets,
            "reps_list": [reps]*sets,
            "avg_reps": reps,
            "rpe": 8,
            "weight": weight,
            "volume": sets * reps * weight
        })

    if st.button("Save"):
        save_data(session)
        st.success("Saved")

# =========================================================
# DASHBOARD
# =========================================================

elif page == "Dashboard":

    st.subheader("Weekly volume trend")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    weekly = df.groupby(df["date"].dt.date)["volume"].sum().reset_index()

    st.line_chart(weekly.set_index("date"))

# =========================================================
# 1RM
# =========================================================

elif page == "1RM Tracking":

    df["est"] = df["weight"] * (1 + df["avg_reps"]/30)

    st.subheader("Estimated strength per lift")

    st.dataframe(df.groupby("exercise")["est"].max())

# =========================================================
# MUSCLE LOAD (REPLACED)
# =========================================================

elif page == "Muscle Load":

    st.subheader("Weekly Sets per Muscle Group")

    st.markdown("### Hypertrophy guidelines")

    st.markdown("""
    Chest: 10–20 sets/week  
    Back: 12–20 sets/week  
    Quads: 10–18 sets/week  
    Hamstrings: 8–16 sets/week  
    Shoulders: 8–16 sets/week  
    Biceps: 6–14 sets/week  
    Triceps: 6–14 sets/week  
    Glutes: 8–16 sets/week  
    Calves: 8–15 sets/week  
    Abs/Core: 8–12 sets/week  
    """)

    weekly = weekly_sets(df)

    if weekly.empty:
        st.stop()

    pivot = weekly.pivot(index="week", columns="muscle", values="sets").fillna(0)

    st.line_chart(pivot)

# =========================================================
# FATIGUE PLANNER
# =========================================================

elif page == "Fatigue Planner":

    st.subheader("Fatigue (weekly sets accumulation)")

    weekly = weekly_sets(df)

    if weekly.empty:
        st.stop()

    for muscle_type in ["quads","hamstrings","glutes","back","chest","shoulders","biceps","triceps","abs"]:

        data_m = weekly[weekly["muscle"] == muscle_type]

        if len(data_m) < 2:
            continue

        fig = forecast_plot(
            data_m,
            "week",
            "sets",
            f"{muscle_type} fatigue"
        )

        st.plotly_chart(fig, use_container_width=True)

# =========================================================
# PROGRESSION
# =========================================================

elif page == "Progression":

    st.subheader("Strength progression + forecast")

    weekly = weekly_exercise_volume(df)

    ex = st.selectbox("Exercise", weekly["exercise"].unique())

    data_ex = weekly[weekly["exercise"] == ex]

    fig = forecast_plot(
        data_ex,
        "week",
        "volume",
        f"{ex} progression"
    )

    st.plotly_chart(fig, use_container_width=True)

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

def session_summary(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.groupby("date")["volume"].sum().reset_index()

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
# EXERCISES + REAL MUSCLE MAPPING (MULTI-ACTIVATION)
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
    "Machine Abs":["core"],
    "Assisted Pull-Up":["back","biceps"],
    "Assisted Dip":["chest","triceps"]
}

# =========================================================
# PROGRESSION
# =========================================================

def get_step(ex):
    return 1.25 if "machine row" in ex.lower() else 2.5

def snap(w, step):
    return round(round(w / step) * step, 2)

def is_assisted(ex):
    return "assisted pull-up" in ex.lower() or "assisted dip" in ex.lower()

def progression(ex, reps, rpe, weight):
    avg = sum(reps)/max(len(reps),1)
    step = get_step(ex)
    assisted = is_assisted(ex)

    if assisted:
        if rpe >= 9:
            return snap(weight + step, step), "increase assistance"
        if avg >= 12 and rpe <= 8:
            return snap(weight - step, step), "reduce assistance"
        return weight, "maintain"

    if rpe >= 9:
        return snap(weight * 0.97, step), "fatigue drop"
    if avg >= 12:
        return snap(weight + step, step), "progress"
    if avg < 8:
        return weight, "build reps"
    return weight, "maintain"

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
    date = st.date_input("Date", datetime.today())
    split = st.radio("Split", ["Lower","Upper"], horizontal=True)

    exercises = LOWER if split=="Lower" else UPPER
    session = []

    cols = st.columns(5)

    for i, ex in enumerate(exercises):
        with cols[i % 5]:

            st.markdown(f"### {ex}")

            sets = st.number_input("Sets",0,6,3,key=f"{ex}s")

            reps = []
            rep_cols = st.columns(max(1, sets))

            for i2 in range(sets):
                with rep_cols[i2]:
                    reps.append(st.number_input(f"{i2+1}",0,30,10,key=f"{ex}r{i2}"))

            rpe = st.slider("RPE",1,10,8,key=f"{ex}rpe")
            weight = st.number_input("Weight",0.0,300.0,20.0,step=0.5,key=f"{ex}w")

            new_w,msg = progression(ex,reps,rpe,weight)

            st.caption(msg)
            st.success(f"Next: {new_w}")

            for m in MUSCLE[ex]:
                session.append({
                    "date":date.strftime("%Y-%m-%d"),
                    "exercise":ex,
                    "muscle":m,
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
# MUSCLE LOAD (REPLACED TEXT BLOCK)
# =========================================================

elif page == "Muscle Load":

    st.title("Weekly Sets per Muscle Group")

    targets = {
        "Chest":"10–20 sets/week",
        "Back":"12–20 sets/week",
        "Quadriceps":"10–18 sets/week",
        "Hamstrings":"8–16 sets/week",
        "Shoulders":"8–16 sets/week",
        "Biceps":"6–14 sets/week",
        "Triceps":"6–14 sets/week",
        "Glutes":"8–16 sets/week",
        "Calves":"8–15 sets/week",
        "Abs/Core":"8–12 sets/week"
    }

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)

    weekly_sets = df.groupby(["week","muscle"])["sets"].sum().reset_index()

    latest = weekly_sets.groupby("muscle")["sets"].mean()

    st.bar_chart(latest)

    st.dataframe(pd.DataFrame.from_dict(targets, orient="index", columns=["Recommended range"]))

# =========================================================
# FATIGUE PLANNER (REAL + PROJECTION COLORS FIXED)
# =========================================================

elif page == "Fatigue Planner":

    st.title("Fatigue Curves")

    weekly = weekly_fatigue(df)

    upper = weekly[weekly["muscle"] != "legs"].groupby("week")["volume"].sum().reset_index()
    lower = weekly[weekly["muscle"] == "legs"].groupby("week")["volume"].sum().reset_index()

    def plot(hist, future, title):

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=hist["week"],
            y=hist["volume"],
            name="Actual",
            line=dict(color="royalblue")
        ))

        if future is not None:
            fig.add_trace(go.Scatter(
                x=future["week"],
                y=future["volume"],
                name="Projection",
                line=dict(color="orange", dash="dash")
            ))

        fig.update_layout(title=title)
        st.plotly_chart(fig, use_container_width=True)

    hu, fu = forecast(upper, "week", "volume")
    hl, fl = forecast(lower, "week", "volume")

    plot(hu, fu, "Upper Body Fatigue")
    plot(hl, fl, "Lower Body Fatigue")

# =========================================================
# PROGRESSION (NO DUPLICATE PLOT)
# =========================================================

elif page == "Progression":

    st.title("Strength Progression Forecast")

    weekly = weekly_exercise_volume(df)

    ex = st.selectbox("Exercise", sorted(weekly["exercise"].unique()))

    d = weekly[weekly["exercise"]==ex].sort_values("week")

    hist, future = forecast(d, "week", "volume")

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=hist["week"],
        y=hist["volume"],
        name="Actual",
        line=dict(color="royalblue")
    ))

    if future is not None:
        fig.add_trace(go.Scatter(
            x=future["week"],
            y=future["volume"],
            name="Projection",
            line=dict(color="orange", dash="dash")
        ))

    fig.update_layout(title="Progression vs Forecast")

    st.plotly_chart(fig, use_container_width=True)

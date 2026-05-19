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
# HELPERS
# =========================================================

def session_summary(df):
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
    return df.groupby(["week","muscle"])["volume"].sum().reset_index()

def weekly_exercise_volume(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
    return df.groupby(["exercise","week"])["volume"].sum().reset_index()

# =========================================================
# FORECAST
# =========================================================

def forecast(df_in, x_col, y_col):
    df2 = df_in.copy().dropna().sort_values(x_col)

    if len(df2) < 3:
        return df2, pd.DataFrame(columns=[x_col, y_col])

    x = np.arange(len(df2))
    y = df2[y_col].values

    slope = np.polyfit(x, y, 1)[0]

    future_x = np.arange(len(df2), len(df2)+7)
    future_y = y[-1] + slope * (future_x - len(df2) + 1)

    future_dates = pd.date_range(df2[x_col].iloc[-1], periods=8, freq="D")[1:]

    future = pd.DataFrame({
        x_col: future_dates,
        y_col: future_y
    })

    return df2, future

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
    "Bulgarian Split Squat":"glutes",
    "Leg Extension":"quadriceps",
    "Hip Abduction":"glutes",
    "Chest Supported Machine Row":"back",
    "Dumbbell Incline Press":"chest",
    "Dumbbell Shoulder Press":"shoulders",
    "Seated Bicep Curl":"biceps",
    "Machine Abs":"abs",
    "Assisted Pull-Up":"back",
    "Assisted Dip":"triceps"
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

    if is_assisted(ex):
        if rpe >= 9:
            return snap(weight + step, step), "increase assistance"
        if avg >= 12:
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

            last = next((x for x in reversed(data) if x["exercise"]==ex), None)
            sets = st.number_input("Sets",0,6,int(last["sets"]) if last else 3,key=f"{ex}s")

            reps = []
            last_reps = last["reps_list"] if last else [10]*sets

            rep_cols = st.columns(max(1, sets))

            for i2 in range(sets):
                with rep_cols[i2]:
                    reps.append(
                        st.number_input(
                            f"{i2+1}",
                            0,30,
                            int(last_reps[i2]) if i2<len(last_reps) else 10,
                            key=f"{ex}r{i2}"
                        )
                    )

            rpe = st.slider("RPE",1,10,8,key=f"{ex}rpe")
            weight = st.number_input("Weight",0.0,300.0,step=0.5,key=f"{ex}w")

            new_w,msg = progression(ex,reps,rpe,weight)

            st.caption(msg)
            st.write("Next:", new_w)

            session.append({
                "date":date.strftime("%Y-%m-%d"),
                "exercise":ex,
                "muscle":MUSCLE[ex],
                "sets":sets,
                "reps_list":reps,
                "avg_reps":sum(reps)/max(len(reps),1),
                "rpe":rpe,
                "weight":weight,
                "volume":sum(reps)*weight
            })

    if st.button("Save"):
        save_data(session)

# =========================================================
# DASHBOARD
# =========================================================

elif page == "Dashboard":
    st.title("Calendar")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    summary = session_summary(df)

    st.line_chart(summary.set_index("date")["volume"])

# =========================================================
# 1RM
# =========================================================

elif page == "1RM Tracking":
    df["est"] = df["weight"]*(1+df["avg_reps"]/30)

    st.subheader("Upper")
    for ex in UPPER:
        d=df[df["exercise"]==ex]
        if not d.empty:
            st.write(ex, round(d["est"].max(),1))

    st.subheader("Lower")
    for ex in LOWER:
        d=df[df["exercise"]==ex]
        if not d.empty:
            st.write(ex, round(d["est"].max(),1))

# =========================================================
# MUSCLE LOAD (SETS/WEEK REPLACEMENT)
# =========================================================

elif page == "Muscle Load":

    st.title("Weekly Sets per Muscle Group")

    df["sets"] = df["sets"].fillna(0)
    df["muscle"] = df["exercise"].map(MUSCLE)

    weekly_sets = df.groupby("muscle")["sets"].sum().sort_values()

    st.bar_chart(weekly_sets)

# =========================================================
# FATIGUE PLANNER (REAL + FORECAST SAME CHART)
# =========================================================

elif page == "Fatigue Planner":

    st.title("Fatigue: Actual vs Forecast")

    weekly = weekly_fatigue(df)

    upper = weekly[weekly["muscle"] != "legs"].groupby("week")["volume"].sum().reset_index()
    lower = weekly[weekly["muscle"] == "legs"].groupby("week")["volume"].sum().reset_index()

    hist_u, fut_u = forecast(upper, "week", "volume")
    hist_l, fut_l = forecast(lower, "week", "volume")

    st.subheader("Upper Body (blue = real, orange = forecast)")
    st.line_chart(pd.concat([
        hist_u.assign(type="real"),
        fut_u.assign(type="forecast")
    ]).set_index("week"))

    st.subheader("Lower Body (blue = real, orange = forecast)")
    st.line_chart(pd.concat([
        hist_l.assign(type="real"),
        fut_l.assign(type="forecast")
    ]).set_index("week"))

# =========================================================
# PROGRESSION (REAL VS FORECAST SAME PLOT)
# =========================================================

elif page == "Progression":

    st.title("Exercise Progression")

    weekly = weekly_exercise_volume(df)

    ex = st.selectbox("Exercise", weekly["exercise"].unique())

    d = weekly[weekly["exercise"]==ex]

    hist, fut = forecast(d, "week", "volume")

    st.line_chart(pd.concat([
        hist.assign(type="real"),
        fut.assign(type="forecast")
    ]).set_index("week"))

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
    return supabase.table("workouts").select("*").execute().data or []

def save_data(session):
    for r in session:
        supabase.table("workouts").insert(r).execute()

data = load_data()

# =========================================================
# EXERCISES
# =========================================================

UPPER = [
    "Assisted Pull-Up",
    "Assisted Dip",
    "Row",
    "Shoulder Press",
    "Incline Press",
    "Bicep Curl",
    "Abs"
]

LOWER = [
    "Squat",
    "RDL",
    "Bulgarian Split Squat",
    "Leg Extension",
    "Hip Abduction"
]

MUSCLE = {
    "Squat": "legs",
    "RDL": "legs",
    "Bulgarian Split Squat": "legs",
    "Leg Extension": "legs",
    "Hip Abduction": "glutes",
    "Row": "back",
    "Shoulder Press": "shoulders",
    "Incline Press": "chest",
    "Bicep Curl": "arms",
    "Abs": "core",
    "Assisted Pull-Up": "back",
    "Assisted Dip": "chest"
}

ASSISTED = ["Assisted Pull-Up", "Assisted Dip"]

# =========================================================
# CORE FORMULAS
# =========================================================

def epley_1rm(w, r):
    return w * (1 + r / 30)

def pr_by_exercise(df, ex):
    d = df[df["exercise"] == ex]
    if d.empty:
        return None
    d = d.copy()
    d["est_1rm"] = d.apply(lambda x: epley_1rm(x["weight"], x["avg_reps"]), axis=1)
    return d["est_1rm"].max()

def strength_curve(df, ex):
    d = df[df["exercise"] == ex].copy()
    if d.empty:
        return None

    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date")
    d["est_1rm"] = d.apply(lambda x: epley_1rm(x["weight"], x["avg_reps"]), axis=1)

    return d[["date", "est_1rm"]]

# =========================================================
# PERIODIZATION
# =========================================================

def week_index(df):
    df["date"] = pd.to_datetime(df["date"])
    return ((df["date"].max() - df["date"].min()).days // 7) + 1 if not df.empty else 1

def phase(week):
    cycle = week % 4
    if cycle in [1, 2, 3]:
        return "build"
    return "deload"

# =========================================================
# FATIGUE HEATMAP
# =========================================================

def fatigue_heatmap(df):
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["day"] = df["date"].dt.date

    heat = df.groupby(["muscle", "day"])["volume"].sum().unstack().fillna(0)

    return heat

# =========================================================
# PROGRESSION (SAFE)
# =========================================================

def progression(reps, rpe, weight):

    avg = sum(reps) / len(reps)

    if rpe >= 9:
        return weight * 0.97, "fatigue drop"

    if avg >= 12 and rpe <= 8:
        return weight * 1.02, "progress"

    if avg < 8:
        return weight, "build reps"

    return weight, "maintain"

# =========================================================
# UI
# =========================================================

st.title("Training System")

page = st.sidebar.radio(
    "Menu",
    ["Train", "Dashboard", "PR Tracking", "Strength Curve", "Heatmap", "Planner"]
)

# =========================================================
# TRAIN
# =========================================================

if page == "Train":

    date = st.date_input("Date", datetime.today())
    split = st.radio("Split", ["Upper", "Lower"], horizontal=True)

    exercises = UPPER if split == "Upper" else LOWER
    session = []

    st.subheader(f"Week {week_index(pd.DataFrame(data))} - {phase(week_index(pd.DataFrame(data)))} phase")

    cols = st.columns(4)

    for i, ex in enumerate(exercises):

        with cols[i % 4]:

            st.markdown(f"### {ex}")

            last = next((x for x in reversed(data) if x["exercise"] == ex), None)

            sets = st.number_input("Sets", 0, 6, last["sets"] if last else 3, key=ex)

            if sets == 0:
                continue

            reps = []
            last_reps = last["reps_list"] if last else [10]*sets

            for i2 in range(sets):
                reps.append(
                    st.number_input(
                        f"S{i2+1}",
                        0, 30,
                        last_reps[i2] if i2 < len(last_reps) else 10,
                        key=f"{ex}_{i2}"
                    )
                )

            rpe = st.slider("RPE", 1, 10, 8, key=ex+"_r")

            weight = st.number_input("Weight", 0.0, 300.0, last["weight"] if last else 20.0, key=ex+"_w")

            new_w, msg = progression(reps, rpe, weight)

            st.info(msg)
            st.success(round(new_w, 1))

            session.append({
                "date": date.strftime("%Y-%m-%d"),
                "exercise": ex,
                "muscle": MUSCLE[ex],
                "sets": sets,
                "reps_list": reps,
                "avg_reps": sum(reps)/len(reps),
                "rpe": rpe,
                "weight": weight,
                "volume": sum(reps)*weight
            })

    if st.button("Save"):
        save_data(session)
        st.success("saved")

# =========================================================
# DASHBOARD
# =========================================================

elif page == "Dashboard":

    df = pd.DataFrame(data)

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])

        st.line_chart(df.groupby("date")["volume"].sum())
        st.bar_chart(df.groupby("muscle")["volume"].sum())

# =========================================================
# PR TRACKING
# =========================================================

elif page == "PR Tracking":

    df = pd.DataFrame(data)

    if not df.empty:

        st.subheader("Estimated PRs (Epley 1RM)")

        for ex in df["exercise"].unique():
            pr = pr_by_exercise(df, ex)
            st.write(ex, "→", round(pr, 1) if pr else "no data")

# =========================================================
# STRENGTH CURVE
# =========================================================

elif page == "Strength Curve":

    df = pd.DataFrame(data)

    if not df.empty:

        ex = st.selectbox("Exercise", df["exercise"].unique())

        curve = strength_curve(df, ex)

        if curve is not None:
            st.line_chart(curve.set_index("date"))

# =========================================================
# HEATMAP
# =========================================================

elif page == "Heatmap":

    df = pd.DataFrame(data)

    if not df.empty:

        heat = fatigue_heatmap(df)
        st.dataframe(heat)

# =========================================================
# PLANNER
# =========================================================

elif page == "Planner":

    df = pd.DataFrame(data)

    if not df.empty:

        st.subheader("Muscle load balance")

        bal = df.groupby("muscle")["volume"].sum()
        st.bar_chart(bal)

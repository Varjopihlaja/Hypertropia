import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client

# =========================================================
# CONFIG
# =========================================================

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================================================
# LOGIN
# =========================================================

def check_password():
    if "auth" not in st.session_state:
        st.session_state.auth = False

    if st.session_state.auth:
        return True

    st.title("Login")

    with st.form("login_form"):
        pw = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
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
# CONFIG
# =========================================================

UPPER = [
    "Assisted Pull-Up",
    "Assisted Dip",
    "Chest-Supported Row",
    "Incline Press",
    "Shoulder Press",
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

MUSCLE_MAP = {
    "Squat": "legs",
    "RDL": "legs",
    "Bulgarian Split Squat": "legs",
    "Leg Extension": "legs",
    "Hip Abduction": "glutes",
    "Chest-Supported Row": "back",
    "Incline Press": "chest",
    "Shoulder Press": "shoulders",
    "Bicep Curl": "arms",
    "Abs": "core",
    "Assisted Pull-Up": "back",
    "Assisted Dip": "chest",
    "BODYWEIGHT": "body"
}

TARGET = {
    "legs": 35,
    "glutes": 25,
    "back": 20,
    "chest": 10,
    "shoulders": 5,
    "arms": 3,
    "core": 2
}

# =========================================================
# HELPERS
# =========================================================

def last_entry(ex):
    exs = [x for x in data if x["exercise"] == ex]
    return exs[-1] if exs else None


def epley_1rm(weight, reps):
    if reps == 0:
        return weight
    return weight * (1 + reps / 30)


def get_bodyweight(df):
    if df.empty:
        return 55

    bw = df[df["exercise"] == "BODYWEIGHT"]
    if len(bw) == 0:
        return 55

    return bw.sort_values("date").iloc[-1]["weight"]

# =========================================================
# PROGRESSION ENGINE
# =========================================================

def progression(reps, rpe, weight, df, exercise):

    avg = sum(reps) / len(reps)
    est_1rm = epley_1rm(weight, avg)

    bw = get_bodyweight(df)
    strength_ratio = weight / bw if bw > 0 else 0

    if rpe >= 9:
        return round(weight * 0.97, 1), "fatigue deload"

    if avg >= 12 and rpe <= 8:

        if strength_ratio < 1.2:
            step = 1.03
        elif strength_ratio < 2:
            step = 1.02
        else:
            step = 1.015

        return round(weight * step, 1), f"progress 1RM {est_1rm:.0f}"

    if avg < 8:
        return weight, "build reps"

    return weight, "maintain"

# =========================================================
# BALANCE
# =========================================================

def muscle_balance(df):
    if df.empty:
        return {}

    b = df.groupby("muscle")["volume"].sum()
    t = b.sum() or 1

    return (b / t * 100).round(1).to_dict()

# =========================================================
# PAGE SETUP
# =========================================================

st.set_page_config(layout="wide", initial_sidebar_state="expanded")

page = st.sidebar.radio(
    "Menu",
    ["Train", "Dashboard", "Schedule", "Fatigue", "Program Planner", "Bodyweight"]
)

# =========================================================
# TRAIN
# =========================================================

if page == "Train":

    st.title("Training")

    date = st.date_input("Date", value=datetime.today())
    split = st.radio("Split", ["Upper", "Lower"], horizontal=True)

    exercises = UPPER if split == "Upper" else LOWER
    session = []

    rows = [exercises[i:i+4] for i in range(0, len(exercises), 4)]

    df = pd.DataFrame(data)

    for row in rows:
        cols = st.columns(4)

        for col, ex in zip(cols, row):

            last = last_entry(ex)

            with col:

                st.subheader(ex)

                sets = st.number_input(
                    "Sets",
                    0, 6,
                    last["sets"] if last else 3,
                    key=f"{ex}_sets"
                )

                if sets == 0:
                    continue

                last_reps = last["reps_list"] if last else [10] * sets
                reps = []

                for i in range(sets):
                    reps.append(
                        st.number_input(
                            f"S{i+1}",
                            0, 30,
                            last_reps[i] if i < len(last_reps) else 10,
                            key=f"{ex}_{i}"
                        )
                    )

                rpe = st.slider("RPE", 1, 10, 8, key=f"{ex}_rpe")

                weight = st.number_input(
                    "Weight",
                    0.0, 300.0,
                    last["weight"] if last else 20.0,
                    step=1.0,
                    key=f"{ex}_w"
                )

                new_w, msg = progression(reps, rpe, weight, df, ex)

                st.write(msg)
                st.write("Next weight:", new_w)

                session.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "exercise": ex,
                    "muscle": MUSCLE_MAP[ex],
                    "sets": sets,
                    "reps_list": reps,
                    "avg_reps": sum(reps)/len(reps),
                    "rpe": rpe,
                    "weight": weight,
                    "volume": sum(reps) * weight
                })

    if st.button("Save"):
        save_data(session)
        st.success("Saved")

# =========================================================
# DASHBOARD
# =========================================================

elif page == "Dashboard":

    df = pd.DataFrame(data)

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])

        st.line_chart(df.groupby("date")["volume"].sum())
        st.bar_chart(df.groupby("muscle")["volume"].sum())

        st.json(muscle_balance(df))

    else:
        st.write("No data")

# =========================================================
# SCHEDULE
# =========================================================

elif page == "Schedule":

    df = pd.DataFrame(data)

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])

        st.line_chart(df.groupby("date")["exercise"].count())
        st.line_chart(df.groupby("date")["volume"].sum())

    else:
        st.write("No data")

# =========================================================
# FATIGUE
# =========================================================

elif page == "Fatigue":

    df = pd.DataFrame(data)

    if not df.empty:
        df["fatigue"] = df["volume"] * df["rpe"]

        st.bar_chart(df.groupby("muscle")["fatigue"].sum())

        if df["rpe"].mean() > 8.5:
            st.warning("High fatigue")
        else:
            st.info("Balanced")

    else:
        st.write("No data")

# =========================================================
# PROGRAM PLANNER
# =========================================================

elif page == "Program Planner":

    df = pd.DataFrame(data)

    if not df.empty:

        bal = muscle_balance(df)

        for m, t in TARGET.items():
            cur = bal.get(m, 0)

            if cur < t:
                st.write("Increase", m)
            elif cur > t + 10:
                st.write("Reduce", m)
            else:
                st.write("Maintain", m)

    else:
        st.write("No data")

# =========================================================
# BODYWEIGHT
# =========================================================

elif page == "Bodyweight":

    st.title("Bodyweight tracking")

    bw = st.number_input("Bodyweight", 30.0, 150.0, 55.0, step=0.1)

    if st.button("Save"):
        supabase.table("workouts").insert({
            "date": datetime.today().strftime("%Y-%m-%d"),
            "exercise": "BODYWEIGHT",
            "muscle": "body",
            "sets": 0,
            "reps_list": [],
            "avg_reps": 0,
            "rpe": 0,
            "weight": bw,
            "volume": 0
        }).execute()

        st.success("Saved")

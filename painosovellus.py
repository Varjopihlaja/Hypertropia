import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

# ---------------- PASSWORD ---------------- #

APP_PASSWORD = st.secrets.get("APP_PASSWORD", "kissa")

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.title("🔐 Enter Password")
    pw = st.text_input("Password", type="password")

    if st.button("Login"):
        if pw == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Wrong password")

    return False

if not check_password():
    st.stop()

# ---------------- STORAGE ---------------- #

DATA_FILE = "workouts.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

data = load_data()

# ---------------- CONFIG ---------------- #

UPPER = [
    "Assisted Pull-Up",
    "Assisted Dip",
    "Row",
    "Shoulder Press",
    "Bicep Curl",
    "Incline Press",
    "Abs"
]

LOWER = [
    "RDL",
    "Squat",
    "Bulgarian Split Squat",
    "Leg Extension"
]

ASSISTED_EXERCISES = ["Assisted Pull-Up", "Assisted Dip"]

MUSCLE_MAP = {
    "Assisted Pull-Up": "back",
    "Assisted Dip": "chest",
    "Row": "back",
    "Shoulder Press": "shoulders",
    "Bicep Curl": "arms",
    "Incline Press": "chest",
    "Abs": "core",
    "RDL": "legs",
    "Squat": "legs",
    "Bulgarian Split Squat": "legs",
    "Leg Extension": "legs"
}

# ---------------- AI LOGIC ---------------- #

def ai_progression(history, weight, reps_list, rpe, exercise):

    avg_reps = sum(reps_list) / len(reps_list)
    fatigue_drop = reps_list[0] - reps_list[-1]

    if len(history) < 3:
        return weight, "🟡 baseline"

    hist = history.tail(5)

    avg_hist_reps = hist["avg_reps"].mean()
    avg_hist_rpe = hist["rpe"].mean()

    # ---- Assisted ---- #
    if exercise in ASSISTED_EXERCISES:

        if avg_reps > avg_hist_reps and rpe <= avg_hist_rpe:
            return round(weight * 0.93, 1), "🟢 reduce assistance"

        if rpe > avg_hist_rpe + 1:
            return round(weight * 1.05, 1), "🔴 increase assistance"

        return weight, "⚪ maintain"

    # ---- Normal ---- #
    if rpe >= 9:
        return round(weight * 0.93, 1), "🔴 deload"

    if avg_reps > avg_hist_reps and rpe <= avg_hist_rpe:
        return round(weight * 1.07, 1), "🟢 increase load"

    if fatigue_drop >= 4:
        return round(weight * 0.95, 1), "🟠 fatigue → reduce"

    return weight, "⚪ maintain"

# ---------------- UI ---------------- #

st.set_page_config(layout="wide")
st.title("🏋️ AI Gym Coach")

page = st.sidebar.radio("Menu", ["🏋️ Train", "📊 Progress"])

# =========================================================
# TRAIN
# =========================================================

if page == "🏋️ Train":

    selected_date = st.date_input("Workout Date", value=datetime.today())

    split = st.radio("Workout Type", ["Upper", "Lower"], horizontal=True)

    exercises = UPPER if split == "Upper" else LOWER

    session = []

    for ex in exercises:

        with st.expander(ex):

            col1, col2, col3 = st.columns(3)

            with col1:
                sets = st.number_input("Sets", 1, 6, 3, key=ex+"sets")

            # ---- reps per set ---- #
            reps_list = []
            cols = st.columns(sets)

            for i in range(sets):
                with cols[i]:
                    r = st.number_input(f"S{i+1}", 0, 30, 10, key=ex+f"r{i}")
                    reps_list.append(r)

            with col2:
                rpe = st.slider("RPE", 1, 10, 8, key=ex+"rpe")

            with col3:
                if ex in ASSISTED_EXERCISES:
                    weight = st.number_input("Assistance (kg)", 0.0, 150.0, 40.0, key=ex+"w")
                else:
                    weight = st.number_input("Weight (kg)", 0.0, 300.0, 20.0, key=ex+"w")

            history = pd.DataFrame([x for x in data if x["exercise"] == ex])

            suggestion, verdict = ai_progression(history, weight, reps_list, rpe, ex)

            st.info(f"{verdict} → {suggestion} kg")

            session.append({
                "date": selected_date.strftime("%d %B %Y"),
                "exercise": ex,
                "muscle": MUSCLE_MAP[ex],
                "sets": sets,
                "reps_list": reps_list,
                "avg_reps": sum(reps_list)/len(reps_list),
                "rpe": rpe,
                "weight": weight,
                "volume": sum(reps_list) * weight,
                "suggestion": suggestion,
                "verdict": verdict
            })

    if st.button("💾 Save Workout"):
        data.extend(session)
        save_data(data)
        st.success(f"{split} workout saved")

# =========================================================
# PROGRESS
# =========================================================

elif page == "📊 Progress":

    if data:

        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"], format="%d %B %Y")

        st.markdown("### Volume Over Time")
        st.line_chart(df.groupby("date")["volume"].sum())

        st.markdown("### Volume by Muscle")
        st.bar_chart(df.groupby("muscle")["volume"].sum())

        ex = st.selectbox("Exercise", df["exercise"].unique())
        ex_df = df[df["exercise"] == ex].sort_values("date")

        st.markdown(f"### {ex} Progress")
        st.line_chart(ex_df.set_index("date")["weight"])
        st.line_chart(ex_df.set_index("date")["avg_reps"])

        st.dataframe(ex_df.tail(10))

    else:
        st.write("No data yet.")

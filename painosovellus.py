import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

# =========================================================
# 🔐 PASSWORD
# =========================================================

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

# =========================================================
# 💾 STORAGE
# =========================================================

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

# =========================================================
# 🧠 CONFIG
# =========================================================

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

# =========================================================
# 🔁 HELPERS
# =========================================================

def get_last_entry(data, exercise):
    entries = [x for x in data if x["exercise"] == exercise]
    return entries[-1] if entries else None

def session_summary(session):

    df = pd.DataFrame(session)
    summary = []

    avg_rpe = df["rpe"].mean()
    volume_by_muscle = df.groupby("muscle")["volume"].sum()

    if avg_rpe >= 8.5:
        summary.append("High fatigue session → reduce intensity next workout.")

    if "chest" in volume_by_muscle and "back" in volume_by_muscle:
        if volume_by_muscle["chest"] > volume_by_muscle["back"] * 1.5:
            summary.append("Chest dominance detected → increase pulling volume.")

    if "legs" in volume_by_muscle and volume_by_muscle["legs"] > 8000:
        summary.append("High leg volume → ensure recovery before next lower day.")

    if avg_rpe < 7:
        summary.append("Session felt easy → increase load next time.")

    if not summary:
        summary.append("Balanced session → good progression.")

    return summary

# =========================================================
# 🧠 AI COACH
# =========================================================

def ai_progression(history, weight, reps_list, rpe, exercise):

    avg_reps = sum(reps_list) / len(reps_list)
    fatigue_drop = reps_list[0] - reps_list[-1]

    if len(history) < 3:
        return weight, "Build consistency first."

    hist = history.tail(5)

    avg_hist_reps = hist["avg_reps"].mean()
    avg_hist_rpe = hist["rpe"].mean()

    if exercise in ASSISTED_EXERCISES:

        if avg_reps > avg_hist_reps and rpe <= avg_hist_rpe:
            return round(weight * 0.93, 1), "Improving → reduce assistance"

        if rpe > avg_hist_rpe + 1:
            return round(weight * 1.05, 1), "Too hard → increase assistance"

        return weight, "Stable → maintain assistance"

    if rpe >= 9:
        return round(weight * 0.93, 1), "High fatigue → deload"

    if avg_reps > avg_hist_reps and rpe <= avg_hist_rpe:
        return round(weight * 1.07, 1), "Progressing → increase load"

    if fatigue_drop >= 4:
        return round(weight * 0.95, 1), "Fatigue drop → reduce slightly"

    return weight, "Stable → small increase possible"

# =========================================================
# 📊 FATIGUE + PROGRAM
# =========================================================

def compute_fatigue(df):
    fatigue = {}
    for m in df["muscle"].unique():
        mdf = df[df["muscle"] == m].tail(5)
        fatigue[m] = round(mdf["volume"].sum() * mdf["rpe"].mean() / 10, 1)
    return fatigue

def generate_next_workout(df):
    fatigue = compute_fatigue(df)
    priority = sorted(fatigue, key=fatigue.get)

    selected = []
    for muscle in priority:
        for ex, m in MUSCLE_MAP.items():
            if m == muscle and ex not in selected:
                selected.append(ex)

    return selected[:6]

# =========================================================
# UI
# =========================================================

st.set_page_config(layout="wide")
st.title("🏋️ AI Gym Coach")

page = st.sidebar.radio("Menu", ["🏋️ Train", "📊 Dashboard", "🤖 AI Coach"])

# =========================================================
# 🏋️ TRAIN
# =========================================================

if page == "🏋️ Train":

    selected_date = st.date_input("Workout Date", value=datetime.today())
    split = st.radio("Workout Type", ["Upper", "Lower"], horizontal=True)

    exercises = UPPER if split == "Upper" else LOWER
    session = []

    for ex in exercises:

        last = get_last_entry(data, ex)

        with st.expander(ex):

            col1, col2, col3 = st.columns(3)

            # sets auto-fill
            default_sets = last["sets"] if last else 3
            with col1:
                sets = st.number_input("Sets", 1, 6, default_sets, key=ex+"sets")

            # reps auto-fill
            reps_list = []
            last_reps = last["reps_list"] if last else [10]*sets
            cols = st.columns(sets)

            for i in range(sets):
                default_rep = last_reps[i] if i < len(last_reps) else 10
                with cols[i]:
                    r = st.number_input(f"S{i+1}", 0, 30, default_rep, key=ex+f"r{i}")
                    reps_list.append(r)

            with col2:
                rpe = st.slider("RPE", 1, 10, 8, key=ex+"rpe")

            with col3:
                if ex in ASSISTED_EXERCISES:
                    default_w = last["weight"] if last else 40.0
                    weight = st.number_input("Assistance (kg)", 0.0, 150.0, default_w, key=ex+"w")
                else:
                    default_w = last["weight"] if last else 20.0
                    weight = st.number_input("Weight (kg)", 0.0, 300.0, default_w, key=ex+"w")

            history = pd.DataFrame([x for x in data if x["exercise"] == ex])

            suggestion, verdict = ai_progression(history, weight, reps_list, rpe, ex)

            st.markdown("### 🧠 AI Coach")
            st.write(verdict)

            if ex in ASSISTED_EXERCISES:
                st.success(f"Next assistance: {suggestion} kg")
            else:
                st.success(f"Next weight: {suggestion} kg")

            session.append({
                "date": selected_date.strftime("%d %B %Y"),
                "exercise": ex,
                "muscle": MUSCLE_MAP[ex],
                "sets": sets,
                "reps_list": reps_list,
                "avg_reps": sum(reps_list)/len(reps_list),
                "rpe": rpe,
                "weight": weight,
                "volume": sum(reps_list) * weight
            })

    if st.button("💾 Save Workout"):
        data.extend(session)
        save_data(data)

        st.success(f"{split} workout saved")

        # ---- SESSION COACH ---- #
        st.markdown("## 🧠 Session Coach")

        for s in session_summary(session):
            st.info(s)

# =========================================================
# 📊 DASHBOARD
# =========================================================

elif page == "📊 Dashboard":

    if data:

        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"], format="%d %B %Y")

        st.markdown("### Volume Over Time")
        st.line_chart(df.groupby("date")["volume"].sum())

        st.markdown("### Muscle Volume")
        st.bar_chart(df.groupby("muscle")["volume"].sum())

        ex = st.selectbox("Exercise", df["exercise"].unique())
        ex_df = df[df["exercise"] == ex].sort_values("date")

        st.markdown(f"### {ex} Progress")
        st.line_chart(ex_df.set_index("date")["weight"])
        st.line_chart(ex_df.set_index("date")["avg_reps"])

    else:
        st.write("No data yet.")

# =========================================================
# 🤖 AI COACH
# =========================================================

elif page == "🤖 AI Coach":

    if data:

        df = pd.DataFrame(data)

        st.markdown("## 🧠 Recommended Workout")

        for ex in generate_next_workout(df):
            st.success(ex)

        st.markdown("### Fatigue Map")
        st.json(compute_fatigue(df))

    else:
        st.write("No data yet.")

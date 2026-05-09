import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

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

# ---------------- TRAINING MAP ---------------- #

MUSCLE_MAP = {
    "Dip": "chest",
    "Incline Press": "chest",
    "Pull-Up": "back",
    "Row": "back",
    "Shoulder Press": "shoulders",
    "Bicep Curl": "arms",
    "Abs": "core",
    "Squat": "legs",
    "RDL": "legs",
    "Bulgarian Split Squat": "legs",
    "Leg Extension": "legs"
}

EXERCISES = list(MUSCLE_MAP.keys())

# ---------------- AI CORE ---------------- #

def compute_fatigue(df):
    fatigue = {}

    for muscle in MUSCLE_MAP.values():
        muscle_df = df[df["muscle"] == muscle]

        if len(muscle_df) == 0:
            fatigue[muscle] = 0
            continue

        recent = muscle_df.tail(5)

        volume = recent["volume"].sum()
        rpe = recent["rpe"].mean() if "rpe" in recent else 7

        fatigue_score = volume * (rpe / 10)

        fatigue[muscle] = fatigue_score

    return fatigue

# ---------------- PROGRESSION ENGINE ---------------- #

def ai_progression(history, weight, reps_list, rpe):
    if len(history) < 3:
        return weight, "baseline"

    avg_reps = history["avg_reps"].mean()
    avg_rpe = history["rpe"].mean()

    fatigue_drop = reps_list[0] - reps_list[-1]

    if rpe >= 9:
        return round(weight * 0.93, 1), "deload (fatigue high)"

    if sum(reps_list)/len(reps_list) > avg_reps and rpe <= avg_rpe:
        return round(weight * 1.07, 1), "increase load"

    if fatigue_drop >= 4:
        return round(weight * 0.95, 1), "reduce (intra-set fatigue)"

    return weight, "maintain"

# ---------------- AUTO PROGRAM GENERATOR ---------------- #

def generate_next_workout(df):
    fatigue = compute_fatigue(df)

    sorted_muscles = sorted(fatigue.items(), key=lambda x: x[1])

    # prioritize least fatigued + lagging muscles
    priority = [m for m, _ in sorted_muscles[:3]]

    plan = []

    for ex, muscle in MUSCLE_MAP.items():
        if muscle in priority:
            plan.append(ex)

    return plan[:6]

# ---------------- UI ---------------- #

st.set_page_config(layout="wide")
st.title("🏋️ AI Adaptive Gym Coach (NEXT LEVEL)")

data = load_data()

page = st.sidebar.radio("Mode", ["🏋️ Train", "📊 Analytics", "🤖 AI Program"])

# =========================================================
# TRAIN
# =========================================================

if page == "🏋️ Train":

    selected_date = st.date_input("Workout Date", value=datetime.today())

    session = []

    st.markdown("## 🧩 Adaptive Workout Session")

    for ex in EXERCISES:

        st.markdown(f"### {ex}")

        col1, col2, col3 = st.columns(3)

        with col1:
            sets = st.number_input(f"Sets {ex}", 1, 6, 3, key=ex+"s")

        reps_list = []
        cols = st.columns(sets)

        for i in range(sets):
            with cols[i]:
                r = st.number_input(f"S{i+1}", 0, 30, 10, key=ex+str(i))
                reps_list.append(r)

        with col2:
            rpe = st.slider(f"RPE {ex}", 1, 10, 8, key=ex+"r")

        with col3:
            weight = st.number_input(f"Weight {ex}", 0.0, 300.0, 20.0, key=ex+"w")

        history_df = pd.DataFrame([x for x in data if x["exercise"] == ex])

        suggestion, verdict = ai_progression(history_df, weight, reps_list, rpe)

        muscle = MUSCLE_MAP[ex]

        st.info(f"{verdict} → {suggestion} kg")

        session.append({
            "date": selected_date.strftime("%d %B %Y"),
            "exercise": ex,
            "muscle": muscle,
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
        st.success("Saved")

# =========================================================
# ANALYTICS
# =========================================================

elif page == "📊 Analytics":

    st.markdown("## 📊 Fatigue + Progress Dashboard")

    if data:
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"], format="%d %B %Y")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Volume Over Time")
            st.line_chart(df.groupby("date")["volume"].sum())

        with col2:
            st.markdown("### Muscle Volume")
            st.bar_chart(df.groupby("muscle")["volume"].sum())

        st.markdown("### Exercise Detail")
        ex = st.selectbox("Exercise", df["exercise"].unique())

        ex_df = df[df["exercise"] == ex].sort_values("date")

        st.line_chart(ex_df.set_index("date")["weight"])
        st.line_chart(ex_df.set_index("date")["avg_reps"])

# =========================================================
# AI PROGRAM GENERATOR
# =========================================================

elif page == "🤖 AI Program":

    st.markdown("## 🧠 AI-Generated Next Workout")

    if data:

        df = pd.DataFrame(data)

        next_plan = generate_next_workout(df)

        st.markdown("### Recommended Exercises Today")

        for ex in next_plan:
            st.success(ex)

        st.markdown("### Logic Behind It")

        fatigue = compute_fatigue(df)

        st.json(fatigue)

        st.info("""
- Low fatigue muscles → prioritized  
- High fatigue muscles → temporarily avoided  
- Balance maintained across week  
        """)

    else:
        st.write("No data yet")

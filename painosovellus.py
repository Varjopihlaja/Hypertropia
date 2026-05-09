import streamlit as st
import pandas as pd
import json
from datetime import datetime
import os

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

# ---------------- SMART PROGRESSION ---------------- #

def smart_suggest(weight, reps, rpe, history):
    if len(history) < 3:
        return weight, "baseline"

    last = pd.DataFrame(history[-5:])

    avg_reps = last["reps"].mean()
    avg_rpe = last["rpe"].mean()

    # Strong progress
    if reps > avg_reps and rpe <= avg_rpe:
        return round(weight * 1.07, 1), "increase"

    # Normal progress
    if reps >= avg_reps:
        return round(weight * 1.05, 1), "slight increase"

    # Fatigue
    if rpe > avg_rpe + 1:
        return round(weight * 0.93, 1), "deload"

    return weight, "maintain"

# ---------------- UI ---------------- #

st.title("🏋️ Hypertrophy Tracker (Local Mode)")

day = st.selectbox("Workout Day", ["Upper", "Lower"])

exercises = {
    "Upper": ["Pull-Up", "Dip", "Row", "Shoulder Press", "Bicep Curl", "Incline Press", "Abs"],
    "Lower": ["RDL", "Squat", "Bulgarian Split Squat", "Leg Extension"]
}

data = load_data()
session_entries = []

for ex in exercises[day]:
    st.markdown(f"### {ex}")

    col1, col2, col3 = st.columns(3)

    with col1:
        sets = st.number_input(f"Sets {ex}", 1, 6, 3, key=ex+"s")

    with col2:
        reps = st.number_input(f"Reps {ex}", 0, 30, 10, key=ex+"r")

    with col3:
        rpe = st.slider(f"RPE {ex}", 1, 10, 8, key=ex+"rp")

    weight = st.number_input(f"Weight (kg) {ex}", 0.0, 300.0, 20.0, key=ex+"w")

    history = [x for x in data if x["exercise"] == ex]
    suggestion, action = smart_suggest(weight, reps, rpe, history)

    st.success(f"➡ {action}: {suggestion} kg")

    session_entries.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "exercise": ex,
        "sets": sets,
        "reps": reps,
        "rpe": rpe,
        "weight": weight,
        "volume": sets * reps * weight,
        "suggestion": suggestion,
        "action": action
    })

# ---------------- SAVE ---------------- #

if st.button("💾 Save Workout"):
    data.extend(session_entries)
    save_data(data)
    st.success("Workout saved locally!")

# ---------------- ANALYTICS ---------------- #

st.markdown("## 📊 Progress")

if data:
    df = pd.DataFrame(data)

    st.line_chart(df.groupby("date")["volume"].sum())

    st.markdown("### Exercise Volume")
    st.bar_chart(df.groupby("exercise")["volume"].sum())

    st.markdown("### Recent Workouts")
    st.dataframe(df.tail(20))
else:
    st.write("No data yet. Start training 💪")

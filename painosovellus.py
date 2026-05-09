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

    df = pd.DataFrame(history[-5:])

    avg_reps = df["reps"].mean()
    avg_rpe = df["rpe"].mean()

    if reps > avg_reps and rpe <= avg_rpe:
        return round(weight * 1.07, 1), "increase"

    if reps >= avg_reps:
        return round(weight * 1.05, 1), "slight increase"

    if rpe > avg_rpe + 1:
        return round(weight * 0.93, 1), "deload"

    return weight, "maintain"

# ---------------- UI ---------------- #

st.title("🏋️ Hypertrophy Tracker (With Date Logging)")

day = st.selectbox("Workout Day", ["Upper", "Lower"])

# 📅 GLOBAL DATE INPUT (NEW)
selected_date = st.date_input(
    "Workout Date",
    value=datetime.today()
)

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
        "date": selected_date.strftime("%Y-%m-%d"),  # ✅ USE SELECTED DATE
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
    st.success(f"Workout saved for {selected_date}")

# ---------------- ANALYTICS ---------------- #

st.markdown("## 📊 Progress")

if data:
    df = pd.DataFrame(data)

    df["date"] = pd.to_datetime(df["date"])

    st.line_chart(df.groupby("date")["volume"].sum())

    st.markdown("### Exercise Volume")
    st.bar_chart(df.groupby("exercise")["volume"].sum())

    st.markdown("### Recent Logs")
    st.dataframe(df.sort_values("date", ascending=False).head(20))
else:
    st.write("No data yet.")

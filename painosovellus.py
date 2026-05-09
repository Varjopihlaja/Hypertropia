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

# ---------------- EXERCISES ---------------- #

EXERCISES = {
    "Upper": ["Pull-Up", "Dip", "Row", "Shoulder Press", "Bicep Curl", "Incline Press", "Abs"],
    "Lower": ["RDL", "Squat", "Bulgarian Split Squat", "Leg Extension"]
}

# ---------------- AI COACH CORE ---------------- #

def get_history(data, exercise):
    df = pd.DataFrame([x for x in data if x["exercise"] == exercise])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date")

def ai_coach(history, weight, reps, rpe):
    if len(history) < 3:
        return weight, "🟡 Not enough data → baseline"

    last = history.tail(5)

    avg_reps = last["reps"].mean()
    avg_rpe = last["rpe"].mean()
    trend = last["weight"].diff().mean()

    # --- Fatigue detection --- #
    if rpe > avg_rpe + 1:
        return round(weight * 0.93, 1), "🔴 High fatigue → deload"

    # --- Strong progression --- #
    if reps > avg_reps and rpe <= avg_rpe:
        return round(weight * 1.07, 1), "🟢 Strong progress → increase"

    # --- Mild progress --- #
    if reps >= avg_reps:
        return round(weight * 1.05, 1), "🟢 Progressing → slight increase"

    # --- Plateau --- #
    if abs(trend) < 0.2:
        return round(weight * 1.03, 1), "🟠 Plateau → small increase"

    return weight, "⚪ Maintain"

# ---------------- UI ---------------- #

st.title("🏋️ AI Gym Coach")

day = st.selectbox("Workout Day", ["Upper", "Lower"])

selected_date = st.date_input(
    "Workout Date",
    value=datetime.today()
)

data = load_data()
session = []

st.markdown("## 🧩 Log Workout")

for ex in EXERCISES[day]:
    st.markdown(f"### {ex}")

    col1, col2, col3 = st.columns(3)

    with col1:
        sets = st.number_input(f"Sets {ex}", 1, 6, 3, key=ex+"s")

    with col2:
        reps = st.number_input(f"Reps {ex}", 0, 30, 10, key=ex+"r")

    with col3:
        rpe = st.slider(f"RPE {ex}", 1, 10, 8, key=ex+"rp")

    weight = st.number_input(f"Weight (kg) {ex}", 0.0, 300.0, 20.0, key=ex+"w")

    history = get_history(data, ex)
    suggestion, verdict = ai_coach(history, weight, reps, rpe)

    st.info(f"{verdict} → {suggestion} kg")

    session.append({
        "date": selected_date.strftime("%d %B %Y"),
        "exercise": ex,
        "sets": sets,
        "reps": reps,
        "rpe": rpe,
        "weight": weight,
        "volume": sets * reps * weight,
        "suggestion": suggestion,
        "verdict": verdict
    })

# ---------------- SAVE ---------------- #

if st.button("💾 Save Session"):
    data.extend(session)
    save_data(data)
    st.success("Workout saved")

# ---------------- AI INSIGHTS DASHBOARD ---------------- #

st.markdown("## 🧠 AI Coach Insights")

if data:
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"], format="%d %B %Y")

    # ---- overall volume ---- #
    st.markdown("### 📊 Total Volume Trend")
    st.line_chart(df.groupby("date")["volume"].sum())

    # ---- exercise selector ---- #
    ex = st.selectbox("Select Exercise", df["exercise"].unique())

    ex_df = df[df["exercise"] == ex].sort_values("date")

    st.markdown(f"### 📈 {ex} Progress")

    st.line_chart(ex_df.set_index("date")["weight"])
    st.line_chart(ex_df.set_index("date")["reps"])
    st.line_chart(ex_df.set_index("date")["volume"])

    # ---- AI summary ---- #
    last_5 = ex_df.tail(5)

    if len(last_5) > 2:
        avg_rpe = last_5["rpe"].mean()
        trend = last_5["weight"].diff().mean()

        st.markdown("### 🧠 Coach Summary")

        if avg_rpe > 8.5:
            st.warning("High fatigue detected → consider deload or reduced sets")
        elif trend > 0:
            st.success("Upward strength trend → keep progressing load")
        else:
            st.info("Stable performance → small progressive overload recommended")

else:
    st.write("No data yet. Start training 💪")

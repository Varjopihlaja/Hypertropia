import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime

# ---------------- CONFIG ---------------- #

SUPABASE_URL = "YOUR_URL"
SUPABASE_KEY = "YOUR_KEY"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- SMART PROGRESSION ---------------- #

def get_history(exercise):
    res = supabase.table("workouts") \
        .select("*") \
        .eq("exercise", exercise) \
        .order("date", desc=True) \
        .limit(5) \
        .execute()
    return res.data

def smart_suggest(weight, reps, rpe, history):
    if not history:
        return weight, "baseline"

    df = pd.DataFrame(history)

    avg_reps = df["reps"].mean()
    avg_rpe = df["rpe"].mean()

    # Strong progress
    if reps > avg_reps and rpe <= avg_rpe:
        return round(weight * 1.07, 1), "strong increase"

    # Normal progress
    if reps >= avg_reps:
        return round(weight * 1.05, 1), "increase"

    # Fatigue / regression
    if rpe > avg_rpe + 1:
        return round(weight * 0.93, 1), "deload"

    return weight, "maintain"

# ---------------- UI ---------------- #

st.title("🏋️ Hypertrophy Tracker (No Login)")

day = st.selectbox("Workout Day", ["Upper", "Lower"])

exercises = {
    "Upper": ["Pull-Up", "Dip", "Row", "Shoulder Press", "Bicep Curl", "Incline Press", "Abs"],
    "Lower": ["RDL", "Squat", "Bulgarian Split Squat", "Leg Extension"]
}

entries = []

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

    history = get_history(ex)
    suggestion, action = smart_suggest(weight, reps, rpe, history)

    st.success(f"➡ {action}: {suggestion} kg")

    entries.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "exercise": ex,
        "weight": weight,
        "reps": reps,
        "sets": sets,
        "rpe": rpe,
        "volume": sets * reps * weight,
        "suggestion": suggestion,
        "action": action
    })

# ---------------- SAVE ---------------- #

if st.button("💾 Save Workout"):
    supabase.table("workouts").insert(entries).execute()
    st.success("Saved!")

# ---------------- ANALYTICS ---------------- #

st.markdown("## 📊 Progress Overview")

res = supabase.table("workouts").select("*").execute()

if res.data:
    df = pd.DataFrame(res.data)

    st.line_chart(df.groupby("date")["volume"].sum())

    st.markdown("### Muscle Load (simple view)")
    st.bar_chart(df.groupby("exercise")["volume"].sum())

    st.markdown("### Recent Sets")
    st.dataframe(df.tail(15))
else:
    st.write("No data yet.")

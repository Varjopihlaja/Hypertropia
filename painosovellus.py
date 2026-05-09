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

# ---------------- TRAINING PROGRAM ---------------- #

PROGRAM = {
    "Upper": {
        "Push": ["Dip", "Incline Press", "Shoulder Press"],
        "Pull": ["Pull-Up", "Row", "Bicep Curl"],
        "Core": ["Abs"]
    },
    "Lower": {
        "Posterior": ["RDL", "Bulgarian Split Squat"],
        "Quad": ["Squat", "Leg Extension"]
    }
}

# ---------------- AI PROGRESSION ---------------- #

def suggest(weight, reps_list, rpe):
    avg_reps = sum(reps_list) / len(reps_list)
    fatigue = reps_list[0] - reps_list[-1]

    if rpe >= 9:
        return round(weight * 0.93, 1), "🔴 deload (high fatigue)"

    if avg_reps >= 12 and rpe <= 7:
        return round(weight * 1.07, 1), "🟢 increase load"

    if fatigue >= 4:
        return round(weight * 0.95, 1), "🟠 fatigue drop → slight reduce"

    return weight, "⚪ maintain"

# ---------------- UI SETUP ---------------- #

st.set_page_config(page_title="AI Gym Coach", layout="wide")

st.title("🏋️ AI Training System")

data = load_data()

# ---------------- SIDEBAR NAV ---------------- #

page = st.sidebar.radio("Navigation", ["🏋️ Train", "📊 Progress", "📅 Program"])

# =========================================================
# 🏋️ TRAINING PAGE
# =========================================================

if page == "🏋️ Train":

    day = st.selectbox("Workout Day", ["Upper", "Lower"])
    selected_date = st.date_input("Workout Date", value=datetime.today())

    session = []

    st.markdown("## 🧩 Workout Session")

    for group, exercises in PROGRAM[day].items():

        st.markdown(f"### {group}")

        for ex in exercises:

            with st.container():
                st.markdown(f"#### {ex}")

                col1, col2, col3 = st.columns([1,1,2])

                with col1:
                    sets = st.number_input(f"Sets {ex}", 1, 6, 3, key=ex+"s")

                reps_list = []
                st.caption("Reps per set")

                cols = st.columns(sets)
                for i in range(sets):
                    with cols[i]:
                        r = st.number_input(f"S{i+1}", 0, 30, 10, key=ex+f"r{i}")
                        reps_list.append(r)

                with col2:
                    rpe = st.slider(f"RPE {ex}", 1, 10, 8, key=ex+"rp")

                with col3:
                    weight = st.number_input(f"Weight (kg)", 0.0, 300.0, 20.0, key=ex+"w")

                suggestion, verdict = suggest(weight, reps_list, rpe)

                st.info(f"{verdict} → {suggestion} kg")

                session.append({
                    "date": selected_date.strftime("%d %B %Y"),
                    "exercise": ex,
                    "group": group,
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
        st.success("Workout saved")

# =========================================================
# 📊 PROGRESS PAGE
# =========================================================

elif page == "📊 Progress":

    st.markdown("## 📈 Progress Dashboard")

    if data:
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"], format="%d %B %Y")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Total Volume")
            st.line_chart(df.groupby("date")["volume"].sum())

        with col2:
            st.markdown("### Exercise Volume")
            st.bar_chart(df.groupby("exercise")["volume"].sum())

        st.markdown("### Exercise Detail")

        ex = st.selectbox("Select Exercise", df["exercise"].unique())
        ex_df = df[df["exercise"] == ex].sort_values("date")

        st.line_chart(ex_df.set_index("date")["weight"])
        st.line_chart(ex_df.set_index("date")["avg_reps"])

        st.dataframe(ex_df.tail(10))

    else:
        st.write("No data yet")

# =========================================================
# 📅 PROGRAM PAGE
# =========================================================

elif page == "📅 Program":

    st.markdown("## 🧠 Weekly Training Structure")

    st.markdown("""
### Weekly Split
- Day 1: Upper (Push/Pull/Core)
- Day 2: Lower (Posterior/Quad)
- Day 3: Rest or Light Cardio
- Repeat

---

### Why this works
- Balanced push/pull volume
- 2x weekly muscle frequency
- Recovery built in
""")

    st.markdown("### Exercise Groups")

    st.json(PROGRAM)

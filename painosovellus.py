import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

# =========================================================
# 🔐 LOGIN
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

TARGET_REPS_MIN = 8
TARGET_REPS_MAX = 12

DELOAD_FATIGUE_THRESHOLD = 2500
DELOAD_RPE_THRESHOLD = 8.5

# =========================================================
# 🔁 HELPERS
# =========================================================

def get_last_entry(data, exercise):
    entries = [x for x in data if x["exercise"] == exercise]
    return entries[-1] if entries else None


def session_summary(session):
    df = pd.DataFrame(session)
    out = []

    avg_rpe = df["rpe"].mean()
    vol = df.groupby("muscle")["volume"].sum()

    if avg_rpe > 8.5:
        out.append("High fatigue session → reduce load next time")

    if "chest" in vol and "back" in vol:
        if vol["chest"] > vol["back"] * 1.5:
            out.append("Chest > back imbalance → add pulling work")

    if avg_rpe < 7:
        out.append("Low intensity → increase effort next session")

    if not out:
        out.append("Balanced session → good progression")

    return out

# =========================================================
# 🧠 FATIGUE + DELOAD
# =========================================================

def compute_fatigue(df):
    fatigue = {}
    for m in df["muscle"].unique():
        mdf = df[df["muscle"] == m].tail(7)
        fatigue[m] = round(mdf["volume"].sum() * mdf["rpe"].mean() / 10, 1)
    return fatigue


def check_deload(df):
    fatigue = compute_fatigue(df)
    avg_rpe = df["rpe"].mean()

    heavy = [m for m, v in fatigue.items() if v > DELOAD_FATIGUE_THRESHOLD]

    if avg_rpe > DELOAD_RPE_THRESHOLD or len(heavy) >= 2:
        return True, heavy

    return False, heavy

# =========================================================
# 🧠 DOUBLE PROGRESSION AI
# =========================================================

def ai_progression(history, weight, reps_list, rpe, exercise, deload=False):

    avg_reps = sum(reps_list) / len(reps_list)
    in_range = all(TARGET_REPS_MIN <= r <= TARGET_REPS_MAX for r in reps_list)

    if deload:
        return weight, "Deload active → maintain weight"

    if len(history) < 3:
        return weight, "Build consistency"

    # assisted
    if exercise in ASSISTED_EXERCISES:

        if avg_reps < TARGET_REPS_MIN:
            return weight, "Build reps → keep assistance"

        if avg_reps >= TARGET_REPS_MAX and rpe <= 8:
            return round(weight * 0.95, 1), "Reduce assistance"

        return weight, "Maintain assistance"

    # normal
    if rpe >= 9 or avg_reps < TARGET_REPS_MIN:
        return round(weight * 0.95, 1), "Too heavy → reduce"

    if avg_reps < TARGET_REPS_MAX:
        return weight, "Build reps"

    if avg_reps >= TARGET_REPS_MAX and in_range and rpe <= 8:
        return round(weight * 1.025, 1), "Increase weight"

    return weight, "Maintain"

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

    date = st.date_input("Date", value=datetime.today())
    split = st.radio("Split", ["Upper", "Lower"], horizontal=True)

    exercises = UPPER if split == "Upper" else LOWER
    session = []

    for ex in exercises:

        last = get_last_entry(data, ex)

        with st.expander(ex):

            col1, col2, col3 = st.columns(3)

            with col1:
                sets = st.number_input("Sets", 1, 6, last["sets"] if last else 3, key=ex+"s")

            reps_list = []
            last_reps = last["reps_list"] if last else [10]*sets
            cols = st.columns(sets)

            for i in range(sets):
                with cols[i]:
                    r = st.number_input(f"S{i+1}", 0, 30, last_reps[i] if i < len(last_reps) else 10, key=ex+str(i))
                    reps_list.append(r)

            with col2:
                rpe = st.slider("RPE", 1, 10, 8, key=ex+"r")

            with col3:
                if ex in ASSISTED_EXERCISES:
                    weight = st.number_input("Assistance", 0.0, 150.0, last["weight"] if last else 40.0, key=ex+"w")
                else:
                    weight = st.number_input("Weight", 0.0, 300.0, last["weight"] if last else 20.0, key=ex+"w")

            df_hist = pd.DataFrame([x for x in data if x["exercise"] == ex])

            deload, _ = check_deload(pd.DataFrame(data)) if data else (False, [])

            suggestion, verdict = ai_progression(df_hist, weight, reps_list, rpe, ex, deload)

            st.markdown("### 🧠 Coach")
            st.write(verdict)

            st.success(f"Next: {suggestion}")

            session.append({
                "date": date.strftime("%d %B %Y"),
                "exercise": ex,
                "muscle": MUSCLE_MAP[ex],
                "sets": sets,
                "reps_list": reps_list,
                "avg_reps": sum(reps_list)/len(reps_list),
                "rpe": rpe,
                "weight": weight,
                "volume": sum(reps_list) * weight
            })

    if st.button("💾 Save"):
        data.extend(session)
        save_data(data)

        st.success("Saved")

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

        st.line_chart(df.groupby("date")["volume"].sum())
        st.bar_chart(df.groupby("muscle")["volume"].sum())

        ex = st.selectbox("Exercise", df["exercise"].unique())
        ex_df = df[df["exercise"] == ex]

        st.line_chart(ex_df.set_index("date")["weight"])
        st.line_chart(ex_df.set_index("date")["avg_reps"])

    else:
        st.write("No data")

# =========================================================
# 🤖 AI COACH
# =========================================================

elif page == "🤖 AI Coach":

    if data:

        df = pd.DataFrame(data)

        st.markdown("## 🧠 Progression Coach")

        deload, heavy = check_deload(df)

        if deload:
            st.error("⚠️ DELoad active")
            st.write("Fatigued:", heavy)
        else:
            st.success("Recovery OK")

        for ex in df["exercise"].unique():

            ex_df = df[df["exercise"] == ex]

            if len(ex_df) < 2:
                continue

            last = ex_df.iloc[-1]
            prev = ex_df.iloc[-2]

            st.markdown(f"### {ex}")

            if ex in ASSISTED_EXERCISES:

                if last["avg_reps"] > prev["avg_reps"]:
                    st.success("Reduce assistance")
                else:
                    st.info("Maintain")

            else:

                if last["avg_reps"] >= TARGET_REPS_MAX and last["rpe"] <= 8:
                    st.success("Increase weight")
                elif last["rpe"] >= 9:
                    st.error("Reduce weight")
                else:
                    st.info("Maintain / build reps")

    else:
        st.write("No data")

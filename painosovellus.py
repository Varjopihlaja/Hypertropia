import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

# =========================================================
# 🔐 LOGIN
# =========================================================

APP_PASSWORD = st.secrets.get("APP_PASSWORD", "1234")

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.title("🔐 Login")
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

ASSISTED = ["Assisted Pull-Up", "Assisted Dip"]

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

TARGET_MIN = 8
TARGET_MAX = 12

DELOAD_FATIGUE = 2500
DELOAD_RPE = 8.5

# =========================================================
# 🔁 HELPERS
# =========================================================

def last_entry(ex):
    items = [x for x in data if x["exercise"] == ex]
    return items[-1] if items else None

# =========================================================
# 📊 FATIGUE + DELOAD
# =========================================================

def compute_fatigue(df):
    out = {}
    for m in df["muscle"].unique():
        mdf = df[df["muscle"] == m].tail(7)
        out[m] = round(mdf["volume"].sum() * mdf["rpe"].mean() / 10, 1)
    return out


def check_deload(df):
    fatigue = compute_fatigue(df)
    avg_rpe = df["rpe"].mean()

    heavy = [m for m, v in fatigue.items() if v > DELOAD_FATIGUE]

    if avg_rpe > DELOAD_RPE or len(heavy) >= 2:
        return True, heavy

    return False, heavy

# =========================================================
# 🟡 PLATEAU SYSTEM
# =========================================================

def detect_plateau(ex_df):
    ex_df = ex_df.sort_values("date")

    if len(ex_df) < 4:
        return False

    recent = ex_df.tail(3)["weight"].mean()
    older = ex_df.head(3)["weight"].mean()

    return abs(recent - older) < 0.5


def plateau_breaker(ex_df):

    if len(ex_df) < 4:
        return "Not enough data"

    avg_rpe = ex_df["rpe"].mean()

    if not detect_plateau(ex_df):
        return "No plateau → continue progression"

    if avg_rpe > 8.5:
        return "🔴 Fatigue plateau → reduce weight ~5% and recover"

    return """
🟡 Plateau detected:

Option 1:
→ Increase reps target (8–12 → 10–15)

Option 2:
→ Maintain weight, improve reps

Option 3:
→ Micro-load increase (+1–2 kg)
"""

# =========================================================
# 🧠 DOUBLE PROGRESSION
# =========================================================

def ai_progression(history, weight, reps, rpe, ex, deload=False):

    avg = sum(reps) / len(reps)
    in_range = all(TARGET_MIN <= r <= TARGET_MAX for r in reps)

    if deload:
        return weight, "Deload → maintain weight"

    if len(history) < 3:
        return weight, "Build consistency"

    if ex in ASSISTED:

        if avg < TARGET_MIN:
            return weight, "Build reps"

        if avg >= TARGET_MAX and rpe <= 8:
            return round(weight * 0.95, 1), "Reduce assistance"

        return weight, "Maintain"

    if rpe >= 9 or avg < TARGET_MIN:
        return round(weight * 0.95, 1), "Too heavy → reduce"

    if avg < TARGET_MAX:
        return weight, "Build reps"

    if avg >= TARGET_MAX and in_range and rpe <= 8:
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

        last = last_entry(ex)

        with st.expander(ex):

            sets = st.number_input("Sets", 1, 6, last["sets"] if last else 3, key=ex)

            reps = []
            last_reps = last["reps_list"] if last else [10]*sets
            cols = st.columns(sets)

            for i in range(sets):
                with cols[i]:
                    reps.append(st.number_input(f"S{i+1}", 0, 30, last_reps[i] if i < len(last_reps) else 10, key=ex+str(i)))

            rpe = st.slider("RPE", 1, 10, 8, key=ex+"r")

            if ex in ASSISTED:
                weight = st.number_input("Assistance", 0.0, 150.0, last["weight"] if last else 40.0)
            else:
                weight = st.number_input("Weight", 0.0, 300.0, last["weight"] if last else 20.0)

            df_hist = pd.DataFrame([x for x in data if x["exercise"] == ex])
            deload, _ = check_deload(pd.DataFrame(data)) if data else (False, [])

            suggestion, verdict = ai_progression(df_hist, weight, reps, rpe, ex, deload)

            st.write(verdict)
            st.success(f"Next: {suggestion}")

            session.append({
                "date": date.strftime("%d %B %Y"),
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
        data.extend(session)
        save_data(data)
        st.success("Saved")

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
        ex_df = df[df["exercise"] == ex].sort_values("date")

        st.line_chart(ex_df.set_index("date")["weight"])
        st.line_chart(ex_df.set_index("date")["avg_reps"])

        st.markdown("### 🟡 Plateau Analysis")
        st.info(plateau_breaker(ex_df))

    else:
        st.write("No data")

# =========================================================
# 🤖 AI COACH
# =========================================================

elif page == "🤖 AI Coach":

    if data:

        df = pd.DataFrame(data)

        st.markdown("## 🧠 Coach Status")

        deload, heavy = check_deload(df)

        if deload:
            st.error("⚠️ Deload active")
            st.write(heavy)
        else:
            st.success("Recovery OK")

        for ex in df["exercise"].unique():

            ex_df = df[df["exercise"] == ex]

            if len(ex_df) < 2:
                continue

            st.markdown(f"### {ex}")

            if detect_plateau(ex_df):
                st.warning(plateau_breaker(ex_df))
            else:
                st.info("Progressing normally")

    else:
        st.write("No data")

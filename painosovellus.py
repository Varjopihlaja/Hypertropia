import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client

# =========================================================
# 🔐 SECRETS
# =========================================================

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================================================
# 🔐 LOGIN
# =========================================================

def check_password():
    if "auth" not in st.session_state:
        st.session_state.auth = False

    if st.session_state.auth:
        return True

    st.title("🔐 Login")
    pw = st.text_input("Password", type="password")

    if st.button("Login"):
        if pw == APP_PASSWORD:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Wrong password")

    return False

if not check_password():
    st.stop()

# =========================================================
# 💾 DATABASE
# =========================================================

def load_data():
    return supabase.table("workouts").select("*").execute().data or []

def save_data(session):
    for r in session:
        supabase.table("workouts").insert(r).execute()

data = load_data()

# =========================================================
# 🧠 TRAINING CONFIG (EXPANDED)
# =========================================================

UPPER = [
    "Assisted Pull-Up",
    "Assisted Dip",
    "Row",
    "Incline Press",
    "Shoulder Press",
    "Bicep Curl",
    "Abs"
]

LOWER = [
    "Squat",
    "RDL",
    "Bulgarian Split Squat",
    "Leg Extension",
    "Hip Abduction",   # NEW
    "Glute Bridge"     # NEW
]

ASSISTED = ["Assisted Pull-Up", "Assisted Dip"]

MUSCLE_MAP = {
    "Squat": "legs",
    "RDL": "legs",
    "Bulgarian Split Squat": "legs",
    "Leg Extension": "legs",
    "Hip Abduction": "glutes",
    "Glute Bridge": "glutes",
    "Row": "back",
    "Incline Press": "chest",
    "Shoulder Press": "shoulders",
    "Bicep Curl": "arms",
    "Abs": "core",
    "Assisted Pull-Up": "back",
    "Assisted Dip": "chest"
}

# Female optimized hypertrophy range
TARGET_MIN = 8
TARGET_MAX = 15

# =========================================================
# 🔁 HELPERS
# =========================================================

def last_entry(ex):
    ex_data = [x for x in data if x["exercise"] == ex]
    return ex_data[-1] if ex_data else None

# =========================================================
# 📈 PERIODIZATION (SIMPLE SMART SYSTEM)
# =========================================================

def progression_logic(avg_reps, rpe, weight, last_weight):

    if rpe >= 9:
        return round(weight * 0.95, 1), "🔴 deload (fatigue)"

    if avg_reps >= TARGET_MAX and rpe <= 8:
        return round(weight * 1.025, 1), "🟢 increase load"

    if avg_reps < TARGET_MIN:
        return weight, "🟡 build reps"

    return weight, "⚪ maintain"

# =========================================================
# 📊 CALENDAR VIEW
# =========================================================

def calendar_view(df):

    st.markdown("## 📅 Training Calendar")

    df["date"] = pd.to_datetime(df["date"])
    days = df.groupby("date")["exercise"].count().reset_index()

    for _, row in days.iterrows():
        st.write(f"📌 {row['date'].date()} → {row['exercise']} exercises")

# =========================================================
# ⚖️ BODY TRACKING
# =========================================================

def body_tracking():
    st.markdown("## ⚖️ Body Tracking (Female Optimized)")
    st.info("Recommended: 55kg / 166cm baseline reference")

    weight = st.number_input("Bodyweight (kg)", 30.0, 120.0, 55.0)
    waist = st.number_input("Waist (cm)", 40.0, 120.0)
    hips = st.number_input("Hips (cm)", 60.0, 140.0)

    if st.button("Save body metrics"):
        supabase.table("body_stats").insert({
            "date": datetime.today().strftime("%Y-%m-%d"),
            "weight": weight,
            "waist": waist,
            "hips": hips
        }).execute()

        st.success("Saved")

# =========================================================
# UI
# =========================================================

st.set_page_config(layout="wide")
st.title("🏋️ AI Gym Coach PRO")

page = st.sidebar.radio(
    "Menu",
    ["🏋️ Train", "📊 Dashboard", "📅 Calendar", "⚖️ Body", "🤖 AI Coach"]
)

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

            sets = st.number_input(
                "Sets", 1, 6,
                value=last["sets"] if last else 3,
                key=f"{ex}_sets"
            )

            reps = []
            last_reps = last["reps_list"] if last else [10]*sets

            cols = st.columns(sets)
            for i in range(sets):
                reps.append(
                    st.number_input(
                        f"Set {i+1}",
                        0, 30,
                        value=last_reps[i] if i < len(last_reps) else 10,
                        key=f"{ex}_rep_{i}"
                    )
                )

            rpe = st.slider("RPE", 1, 10, 8, key=f"{ex}_rpe")

            weight = st.number_input(
                "Weight",
                0.0, 300.0,
                value=last["weight"] if last else 20.0,
                key=f"{ex}_weight"
            )

            avg = sum(reps) / len(reps)

            new_weight, verdict = progression_logic(avg, rpe, weight, last["weight"] if last else weight)

            st.info(verdict)
            st.success(f"Next: {new_weight}")

            session.append({
                "date": date.strftime("%Y-%m-%d"),
                "exercise": ex,
                "muscle": MUSCLE_MAP[ex],
                "sets": sets,
                "reps_list": reps,
                "avg_reps": avg,
                "rpe": rpe,
                "weight": weight,
                "volume": sum(reps) * weight
            })

    if st.button("Save Workout"):
        save_data(session)
        st.success("Saved")

# =========================================================
# 📊 DASHBOARD
# =========================================================

elif page == "📊 Dashboard":

    df = pd.DataFrame(data)

    if not df.empty:

        df["date"] = pd.to_datetime(df["date"])

        st.line_chart(df.groupby("date")["volume"].sum())
        st.bar_chart(df.groupby("muscle")["volume"].sum())

        ex = st.selectbox("Exercise", df["exercise"].unique())
        ex_df = df[df["exercise"] == ex]

        st.line_chart(ex_df.set_index("date")["weight"])

    else:
        st.write("No data")

# =========================================================
# 📅 CALENDAR
# =========================================================

elif page == "📅 Calendar":

    df = pd.DataFrame(data)

    if not df.empty:
        calendar_view(df)
    else:
        st.write("No sessions yet")

# =========================================================
# ⚖️ BODY
# =========================================================

elif page == "⚖️ Body":
    body_tracking()

# =========================================================
# 🤖 AI COACH
# =========================================================

elif page == "🤖 AI Coach":

    df = pd.DataFrame(data)

    if not df.empty:
        st.markdown("## 🧠 Weekly Summary")

        last7 = df[pd.to_datetime(df["date"]) > datetime.today() - timedelta(days=7)]

        st.info(f"Total volume: {last7['volume'].sum():.0f}")

        st.info("Focus: progressive overload + glutes + posterior chain (female optimized)")

    else:
        st.write("No data")

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime, timedelta

from supabase import create_client

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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

def load_data():
    response = supabase.table("workouts").select("*").execute()
    return response.data if response.data else []

data = load_data()

def save_data(session):
    for row in session:
        supabase.table("workouts").insert({
            "date": row["date"],
            "exercise": row["exercise"],
            "muscle": row["muscle"],
            "sets": row["sets"],
            "reps_list": row["reps_list"],
            "avg_reps": row["avg_reps"],
            "rpe": row["rpe"],
            "weight": row["weight"],
            "volume": row["volume"]
        }).execute()

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

# =========================================================
# 🔁 HELPERS
# =========================================================

def last_entry(ex):
    items = [x for x in data if x["exercise"] == ex]
    return items[-1] if items else None

# =========================================================
# 📊 FATIGUE
# =========================================================

def compute_fatigue(df):
    out = {}
    for m in df["muscle"].unique():
        mdf = df[df["muscle"] == m].tail(7)
        out[m] = round(mdf["volume"].sum() * mdf["rpe"].mean() / 10, 1)
    return out

# =========================================================
# 📈 PROGRESSION TRACKING
# =========================================================

def progression_status(ex_df):

    ex_df = ex_df.sort_values("date")

    if len(ex_df) < 3:
        return "insufficient data"

    recent = ex_df.tail(3)["weight"].mean()
    older = ex_df.head(3)["weight"].mean()

    diff = recent - older

    if diff > 1:
        return "🟢 progressing"
    elif diff < -1:
        return "🔴 regressing"
    return "🟡 plateau"

# =========================================================
# 🟡 PLATEAU BREAKER
# =========================================================

def plateau_breaker(ex_df):

    if len(ex_df) < 4:
        return "Not enough data"

    avg_rpe = ex_df["rpe"].mean()

    recent = ex_df.tail(3)["weight"].mean()
    older = ex_df.head(3)["weight"].mean()

    if abs(recent - older) < 0.5:

        if avg_rpe > 8.5:
            return "🔴 Fatigue plateau → deload 5%"
        return "🟡 Plateau → increase reps or micro-load"

    return "No plateau"

# =========================================================
# 🧠 DOUBLE PROGRESSION
# =========================================================

def ai_progression(history, weight, reps, rpe, ex):

    avg = sum(reps) / len(reps)
    in_range = all(TARGET_MIN <= r <= TARGET_MAX for r in reps)

    if len(history) < 3:
        return weight, "Build consistency"

    if ex in ASSISTED:

        if avg < TARGET_MIN:
            return weight, "Build reps"

        if avg >= TARGET_MAX and rpe <= 8:
            return round(weight * 0.95, 1), "Reduce assistance"

        return weight, "Maintain"

    if rpe >= 9 or avg < TARGET_MIN:
        return round(weight * 0.95, 1), "Too heavy"

    if avg < TARGET_MAX:
        return weight, "Build reps"

    if avg >= TARGET_MAX and in_range and rpe <= 8:
        return round(weight * 1.025, 1), "Increase weight"

    return weight, "Maintain"

# =========================================================
# 📅 WEEKLY REPORT
# =========================================================

def weekly_report(df):

    if df.empty:
        return []

    df["date"] = pd.to_datetime(df["date"])

    end = df["date"].max()
    start = end - timedelta(days=7)

    week = df[df["date"] >= start]

    report = []

    report.append(f"📅 Week volume: {week['volume'].sum():.0f}")

    avg_rpe = week["rpe"].mean()
    report.append(f"🔥 Avg intensity: {avg_rpe:.1f}")

    fatigue = compute_fatigue(week)

    most_fatigued = max(fatigue, key=fatigue.get) if fatigue else None

    if most_fatigued:
        report.append(f"⚠️ Most fatigued: {most_fatigued}")

    if avg_rpe > 8.5:
        report.append("🟥 Recommendation: reduce load next week")
    elif avg_rpe < 7:
        report.append("🟨 Recommendation: increase intensity")
    else:
        report.append("🟩 Training load is optimal")

    return report

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

            sets = st.number_input(
                "Sets",
                1, 6,
                last["sets"] if last else 3,
                key=f"{ex}_sets"
            )

            reps = []
            last_reps = last["reps_list"] if last else [10]*sets
            cols = st.columns(sets)

            for i in range(sets):
                reps.append(
                    st.number_input(
                        f"S{i+1}",
                        0, 30,
                        last_reps[i] if i < len(last_reps) else 10,
                        key=f"{ex}_rep_{i}"
                    )
                )

            rpe = st.slider("RPE", 1, 10, 8, key=f"{ex}_rpe")

            if ex in ASSISTED:
                weight = st.number_input(
                    "Assistance",
                    0.0, 150.0,
                    last["weight"] if last else 40.0,
                    key=f"{ex}_weight"
                )
            else:
                weight = st.number_input(
                    "Weight",
                    0.0, 300.0,
                    last["weight"] if last else 20.0,
                    key=f"{ex}_weight"
                )

            df_hist = pd.DataFrame([x for x in data if x["exercise"] == ex])

            suggestion, verdict = ai_progression(df_hist, weight, reps, rpe, ex)

            st.write(verdict)
            st.success(f"Next: {suggestion}")

            session.append({
                "date": date.strftime("%Y-%m-%d"),
                "exercise": ex,
                "muscle": MUSCLE_MAP[ex],
                "sets": sets,
                "reps_list": reps,
                "avg_reps": sum(reps)/len(reps),
                "rpe": rpe,
                "weight": weight,
                "volume": sum(reps) * weight
            })

    if st.button("Save Workout"):
        data.extend(session)
        save_data(data)
        st.success("Saved")

        st.markdown("## 🧠 Weekly-style immediate feedback")
        df = pd.DataFrame(session)
        for r in weekly_report(df):
            st.info(r)

# =========================================================
# 📊 DASHBOARD
# =========================================================

elif page == "📊 Dashboard":

    if data:

        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])

        st.line_chart(df.groupby("date")["volume"].sum())
        st.bar_chart(df.groupby("muscle")["volume"].sum())

        ex = st.selectbox("Exercise", df["exercise"].unique())
        ex_df = df[df["exercise"] == ex]

        st.line_chart(ex_df.set_index("date")["weight"])
        st.line_chart(ex_df.set_index("date")["avg_reps"])

        st.markdown("## 📈 Status")
        st.write(progression_status(ex_df))
        st.info(plateau_breaker(ex_df))

    else:
        st.write("No data")

# =========================================================
# 🤖 AI COACH
# =========================================================

elif page == "🤖 AI Coach":

    if data:

        df = pd.DataFrame(data)

        st.markdown("## 🧠 Weekly Report")

        for r in weekly_report(df):
            st.info(r)

        st.markdown("## 📊 Exercise Status")

        for ex in df["exercise"].unique():

            ex_df = df[df["exercise"] == ex]

            st.write(f"### {ex}")
            st.write(progression_status(ex_df))
            st.info(plateau_breaker(ex_df))

    else:
        st.write("No data")

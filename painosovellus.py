import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client

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

    st.title("Login")

    with st.form("login_form"):
        pw = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
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
# 🧠 CONFIG
# =========================================================

UPPER = [
    "Assisted Pull-Up",
    "Assisted Dip",
    "Chest-Supported Machine Row",
    "Shoulder Dumbbell Press",
    "Incline Dumbbell Press",
    "Bicep Curl Seated",
    "Machine Abs"
]

LOWER = [
    "RDL",
    "Back Squat Full ROM",
    "Bulgarian Split Squat",
    "Leg Extension",
    "Hip Abduction"
]

MUSCLE_MAP = {
    "Back Squat Full ROM": "legs",
    "RDL": "legs",
    "Bulgarian Split Squat": "legs",
    "Leg Extension": "legs",
    "Hip Abduction": "glutes",
    "Chest-Supported Machine Row": "back",
    "Incline Dumbbell Press": "chest",
    "Shoulder Dumbbell Press": "shoulders",
    "Bicep Curl Seated": "arms",
    "Machine Abs": "core",
    "Assisted Pull-Up": "back",
    "Assisted Dip": "chest"
}

TARGET_MIN = 8
TARGET_MAX = 12

# =========================================================
# 🧠 HELPERS
# =========================================================

def estimate_1rm(weight, reps):
    return weight * (1 + reps / 30)

def get_step(ex, weight):
    if "Dumbbell" in ex or "Curl" in ex:
        return 1.0 if weight <= 10 else 2.5
    return 2.5

def round_to_step(weight, step):
    return round(weight / step) * step

def last_entry(ex):
    ex_data = [x for x in data if x["exercise"] == ex]
    return ex_data[-1] if ex_data else None

# =========================================================
# 🧠 PROGRESSION (STRICT + SMART)
# =========================================================

def progression(reps, rpe, weight, ex):

    avg_reps = sum(reps) / len(reps)
    all_sets_hit = all(r >= TARGET_MAX for r in reps)

    step = get_step(ex, weight)
    est_1rm = estimate_1rm(weight, avg_reps)

    # fatigue protection
    if rpe >= 9:
        return round_to_step(weight * 0.97, step), "🔴 fatigue → reduce"

    # STRICT progression rule
    if all_sets_hit and rpe <= 8:
        return round_to_step(weight * 1.03, step), f"🟢 increase (1RM ~ {est_1rm:.1f})"

    # build reps phase
    if avg_reps < TARGET_MAX:
        return weight, "🟡 build reps"

    return weight, "⚪ maintain"

# =========================================================
# UI
# =========================================================

st.set_page_config(layout="centered")
st.title("🏋️ Hypertrophy Coach")

page = st.sidebar.radio("Menu", ["Train", "Dashboard"])

# =========================================================
# 🏋️ TRAIN
# =========================================================

if page == "Train":

    date = st.date_input("Date", value=datetime.today())
    split = st.radio("Split", ["Upper", "Lower"], horizontal=True)

    exercises = UPPER if split == "Upper" else LOWER
    session = []

    for ex in exercises:

        last = last_entry(ex)

        with st.expander(ex):

            sets = st.number_input(
                "Sets",
                0, 6,
                last["sets"] if last else 3,
                key=f"{ex}_sets"
            )

            if sets == 0:
                st.caption("Skipped")
                continue

            reps = []
            last_reps = last["reps_list"] if last else [10]*sets

            for i in range(sets):
                reps.append(
                    st.number_input(
                        f"Set {i+1}",
                        0, 30,
                        last_reps[i] if i < len(last_reps) else 10,
                        key=f"{ex}_rep_{i}"
                    )
                )

            rpe = st.slider("RPE", 1, 10, 8, key=f"{ex}_rpe")

            weight = st.number_input(
                "Weight",
                0.0, 300.0,
                last["weight"] if last else 20.0,
                key=f"{ex}_weight"
            )

            new_w, msg = progression(reps, rpe, weight, ex)

            st.info(msg)
            st.success(f"Next: {new_w} kg")

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
        save_data(session)
        st.success("Saved")

# =========================================================
# 📊 DASHBOARD
# =========================================================

elif page == "Dashboard":

    df = pd.DataFrame(data)

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])

        st.line_chart(df.groupby("date")["volume"].sum())
        st.bar_chart(df.groupby("muscle")["volume"].sum())

        ex = st.selectbox("Exercise", df["exercise"].unique())
        ex_df = df[df["exercise"] == ex]

        st.line_chart(ex_df.set_index("date")["weight"])
        st.line_chart(ex_df.set_index("date")["avg_reps"])

    else:
        st.write("No data")

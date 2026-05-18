import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client


SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def check_password():
    if "auth" not in st.session_state:
        st.session_state.auth = False

    if st.session_state.auth:
        return True

    st.title("Login")

    # IMPORTANT: form enables Enter-to-submit
    with st.form("login_form"):
        pw = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")  # <-- Enter triggers this

    if submitted:
        if pw == APP_PASSWORD:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Wrong password")

    return False

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
# 🧠 CONFIG (EXPANDED)
# =========================================================

UPPER = [
    "Assisted Pull-Up",
    "Assisted Dip",
    "Chest-Supported Machine Row",
    "Incline Dumbbell Press",
    "Shoulder Dumbbell Press",
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

ASSISTED = ["Assisted Pull-Up", "Assisted Dip"]

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
TARGET_MAX = 15

# =========================================================
# 🔁 HELPERS
# =========================================================

def last_entry(ex):
    ex_data = [x for x in data if x["exercise"] == ex]
    return ex_data[-1] if ex_data else None

# =========================================================
# 📈 PERIODIZATION
# =========================================================

def week_number(df):
    df["date"] = pd.to_datetime(df["date"])
    return ((df["date"].max() - df["date"].min()).days // 7) + 1

def is_deload_week(df):
    return week_number(df) % 4 == 0

# =========================================================
# 📊 MUSCLE BALANCE
# =========================================================

def muscle_balance(df):
    if df.empty:
        return {}

    balance = df.groupby("muscle")["volume"].sum().to_dict()
    total = sum(balance.values()) or 1

    return {k: round(v / total * 100, 1) for k, v in balance.items()}

# =========================================================
# 🧠 PROGRESSION (SAFE)
# =========================================================



def progression(avg_reps, rpe, weight):

    est_1rm = estimate_1rm(weight, avg_reps)

    # fatigue protection
    if rpe >= 9:
        return round(weight * 0.97, 1), "🔴 fatigue → deload"

    # strength-based progression (Epley-aware)
    if avg_reps >= 12 and rpe <= 8:
        # small controlled increase
        return round(weight * 1.02, 1), f"🟢 progress (est 1RM {est_1rm:.1f}kg)"

    if avg_reps < 8:
        return weight, "🟡 build reps"

    return weight, "⚪ maintain"

# =========================================================
# 🤖 PROGRAM GENERATOR
# =========================================================

def generate_program(df):

    balance = muscle_balance(df)

    targets = {
        "legs": 35,
        "glutes": 25,
        "back": 20,
        "chest": 10,
        "shoulders": 5,
        "arms": 3,
        "core": 2
    }

    output = []

    for m, t in targets.items():
        cur = balance.get(m, 0)

        if cur < t:
            output.append(f"⬆️ Increase {m}")
        elif cur > t + 10:
            output.append(f"⬇️ Reduce {m}")
        else:
            output.append(f"⚖️ Maintain {m}")

    return output

# =========================================================
# 📅 CALENDAR
# =========================================================

def show_calendar(df):

    df["date"] = pd.to_datetime(df["date"])
    days = df.groupby("date")["exercise"].count().reset_index()

    st.markdown("## Calendar")

    for _, r in days.iterrows():
        st.write(f"📌 {r['date'].date()} → {r['exercise']} exercises")

# =========================================================
# ⚖️ BODY TRACKING
# =========================================================

def body_tracking():

    st.markdown("## Body Tracking")

    weight = st.number_input("Bodyweight (kg)", 30.0, 120.0, 55.0)
    waist = st.number_input("Waist (cm)", 40.0, 120.0)
    hips = st.number_input("Hips (cm)", 60.0, 140.0)

    if st.button("Save"):
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
st.title("🏋️ Hypertrophy coach")

page = st.sidebar.radio(
    "Menu",
    ["Train", "Dashboard", "Calendar", "Body", "AI Coach", "AI Program"]
)

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

            sets = st.number_input("Sets", 1, 6, last["sets"] if last else 3, key=f"{ex}_sets")

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

            weight = st.number_input(
                "Weight",
                0.0, 300.0,
                last["weight"] if last else 20.0,
                key=f"{ex}_weight"
            )

            avg = sum(reps) / len(reps)

            new_w, msg = progression(avg, rpe, weight)

            st.info(msg)
            st.success(f"Next weight: {new_w}")

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

elif page == "Dashboard":

    df = pd.DataFrame(data)

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])

        st.line_chart(df.groupby("date")["volume"].sum())
        st.bar_chart(df.groupby("muscle")["volume"].sum())

    else:
        st.write("No data")

# =========================================================
# 📅 CALENDAR
# =========================================================

elif page == "Calendar":
    df = pd.DataFrame(data)
    if not df.empty:
        show_calendar(df)

# =========================================================
# ⚖️ BODY
# =========================================================

elif page == "Body":
    body_tracking()

# =========================================================
# 🤖 AI COACH
# =========================================================

elif page == "AI Coach":

    df = pd.DataFrame(data)

    if not df.empty:

        st.markdown("## Weekly AI Report")

        last7 = df[pd.to_datetime(df["date"]) > datetime.today() - timedelta(days=7)]

        st.info(f"Volume: {last7['volume'].sum():.0f}")

        bal = muscle_balance(df)
        st.json(bal)

        if is_deload_week(df):
            st.warning("🔴 Deload week active")

    else:
        st.write("No data")

# =========================================================
# 🧠 AI PROGRAM
# =========================================================

elif page == "AI Program":

    df = pd.DataFrame(data)

    if not df.empty:

        st.markdown("## Auto Program")

        if is_deload_week(df):
            st.warning("Deload week → reduce weights 10–20%")

        st.markdown("### Muscle balance")
        st.json(muscle_balance(df))

        st.markdown("### Adjustments")

        for x in generate_program(df):
            st.write(x)

    else:
        st.write("No data")

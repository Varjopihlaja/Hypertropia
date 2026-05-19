import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client

# =========================================================
# CONFIG
# =========================================================

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(layout="wide")

# =========================================================
# AUTH
# =========================================================

def check_password():
    if "auth" not in st.session_state:
        st.session_state.auth = False

    if st.session_state.auth:
        return True

    st.title("Login")

    with st.form("login"):
        pw = st.text_input("Password", type="password")
        ok = st.form_submit_button("Login")

    if ok:
        if pw == APP_PASSWORD:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Wrong password")

    return False


if not check_password():
    st.stop()

# =========================================================
# DATA
# =========================================================

def load_data():
    return supabase.table("workouts").select("*").execute().data or []

def save_data(session):
    for r in session:
        supabase.table("workouts").insert(r).execute()

data = load_data()

def safe_df():
    if not data:
        return pd.DataFrame(columns=["date", "exercise", "muscle", "volume"])
    return pd.DataFrame(data)

df = safe_df()

# =========================================================
# EXERCISES
# =========================================================

UPPER = [
    "Assisted Pull-Up",
    "Assisted Dip",
    "Chest Supported Machine Row",
    "Dumbbell Shoulder Press",
    "Dumbbell Incline Press",
    "Seated Bicep Curl",
    "Machine Abs"
]

LOWER = [
    "Back Squat",
    "RDL",
    "Bulgarian Split Squat",
    "Leg Extension",
    "Hip Abduction"
]

MUSCLE = {
    "Back Squat": "legs",
    "RDL": "legs",
    "Bulgarian Split Squat": "legs",
    "Leg Extension": "legs",
    "Hip Abduction": "glutes",
    "Chest Supported Machine Row": "back",
    "Dumbbell Incline Press": "chest",
    "Dumbbell Shoulder Press": "shoulders",
    "Seated Bicep Curl": "arms",
    "Machine Abs": "core",
    "Assisted Pull-Up": "back",
    "Assisted Dip": "chest"
}

# =========================================================
# WEIGHT SYSTEM (REAL GYM RULES)
# =========================================================

def get_step(ex, weight):
    ex_low = ex.lower()

    if "dumbbell" in ex_low or "curl" in ex_low:
        return 1.0 if weight <= 10 else 2.5

    if "squat" in ex_low or "press" in ex_low or "incline" in ex_low or "rdl" in ex_low:
        return 1.25

    return 2.5


def snap(weight, step):
    return round(round(weight / step) * step, 2)

# =========================================================
# CONSISTENCY CHECK (NEW CORE LOGIC)
# =========================================================

def exercise_history(ex):
    hist = [x for x in data if x["exercise"] == ex]
    hist = sorted(hist, key=lambda x: x["date"], reverse=True)
    return hist[:5]  # last 5 sessions


def is_consistent_progress(ex):
    hist = exercise_history(ex)

    if len(hist) < 3:
        return False

    # must hit 12+ reps in ALL sets for last 3 sessions
    for h in hist[:3]:
        reps = h.get("reps_list", [])
        if not reps:
            return False
        if not all(r >= 12 for r in reps):
            return False

    return True

# =========================================================
# PROGRESSION (FIXED LOGIC)
# =========================================================

def progression(reps, rpe, weight, ex):

    avg = sum(reps) / len(reps)
    step = get_step(ex, weight)

    consistent = is_consistent_progress(ex)

    # fatigue override
    if rpe >= 9:
        return snap(weight - step, step), "fatigue drop"

    # ONLY increase if consistent across multiple sessions
    if consistent and rpe <= 8:
        return snap(weight + step, step), "progress (consistent 12+ reps)"

    # build phase
    if avg < 8:
        return weight, "build reps"

    return weight, "maintain"

# =========================================================
# UI
# =========================================================

st.title("Training System")

page = st.sidebar.radio(
    "Menu",
    ["Train", "Dashboard", "PR Tracking", "Heatmap", "Planner"]
)

# =========================================================
# TRAIN (5 EXERCISES PER ROW)
# =========================================================

if page == "Train":

    date = st.date_input("Date", datetime.today())
    split = st.radio("Split", ["Upper", "Lower"], horizontal=True)

    exercises = UPPER if split == "Upper" else LOWER
    session = []

    st.subheader("Training Session")

    # 5 per row (your request)
    rows = [exercises[i:i+5] for i in range(0, len(exercises), 5)]

    for row in rows:
        cols = st.columns(5)

        for col, ex in zip(cols, row):

            with col:

                st.markdown(f"### {ex}")

                last = next((x for x in reversed(data) if x["exercise"] == ex), None)

                sets = st.number_input(
                    "Sets",
                    0, 6,
                    last["sets"] if last else 3,
                    key=f"{ex}_sets"
                )

                if sets == 0:
                    continue

                reps = []
                last_reps = last["reps_list"] if last else [10] * sets

                for i2 in range(sets):
                    reps.append(
                        st.number_input(
                            f"S{i2+1}",
                            0, 30,
                            last_reps[i2] if i2 < len(last_reps) else 10,
                            key=f"{ex}_{i2}"
                        )
                    )

                rpe = st.slider("RPE", 1, 10, 8, key=f"{ex}_r")

                weight = st.number_input(
                    "Weight",
                    0.0, 300.0,
                    last["weight"] if last else 20.0,
                    key=f"{ex}_w"
                )

                new_w, msg = progression(reps, rpe, weight, ex)

                st.caption(msg)
                st.success(f"{new_w} kg")

                session.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "exercise": ex,
                    "muscle": MUSCLE[ex],
                    "sets": sets,
                    "reps_list": reps,
                    "avg_reps": sum(reps) / len(reps),
                    "rpe": rpe,
                    "weight": snap(weight, get_step(ex, weight)),
                    "volume": sum(reps) * weight
                })

    if st.button("Save"):
        save_data(session)
        st.success("saved")

# =========================================================
# DASHBOARD
# =========================================================

elif page == "Dashboard":

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

        st.line_chart(df.groupby("date")["volume"].sum())
        st.bar_chart(df.groupby("muscle")["volume"].sum())
    else:
        st.write("No data")

# =========================================================
# PR TRACKING (EPLEY 1RM)
# =========================================================

elif page == "PR Tracking":

    if not df.empty:
        df["est_1rm"] = df.apply(
            lambda x: x["weight"] * (1 + x["avg_reps"] / 30),
            axis=1
        )

        for ex in df["exercise"].unique():
            pr = df[df["exercise"] == ex]["est_1rm"].max()
            st.write(ex, "→", round(pr, 1))
    else:
        st.write("No data")

# =========================================================
# HEATMAP
# =========================================================

elif page == "Heatmap":

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["day"] = df["date"].dt.date

        heat = df.groupby(["muscle", "day"])["volume"].sum().unstack().fillna(0)
        st.dataframe(heat)
    else:
        st.write("No data")

# =========================================================
# PLANNER
# =========================================================

elif page == "Planner":

    if not df.empty:
        st.bar_chart(df.groupby("muscle")["volume"].sum())
    else:
        st.write("No data")

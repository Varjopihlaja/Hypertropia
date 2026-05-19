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
    try:
        return supabase.table("workouts").select("*").execute().data or []
    except:
        return []

def save_data(session):
    for r in session:
        supabase.table("workouts").insert(r).execute()

data = load_data()

def safe_df():
    if not data:
        return pd.DataFrame(columns=["date", "exercise", "muscle", "volume"])
    return pd.DataFrame(data)

# =========================================================
# EXERCISES
# =========================================================

UPPER = [
    "Assisted Pull-Up",
    "Assisted Dip",
    "Row",
    "Shoulder Press",
    "Incline Press",
    "Bicep Curl",
    "Abs"
]

LOWER = [
    "Squat",
    "RDL",
    "Bulgarian Split Squat",
    "Leg Extension",
    "Hip Abduction"
]

MUSCLE = {
    "Squat": "legs",
    "RDL": "legs",
    "Bulgarian Split Squat": "legs",
    "Leg Extension": "legs",
    "Hip Abduction": "glutes",
    "Row": "back",
    "Shoulder Press": "shoulders",
    "Incline Press": "chest",
    "Bicep Curl": "arms",
    "Abs": "core",
    "Assisted Pull-Up": "back",
    "Assisted Dip": "chest"
}

# =========================================================
# CORE FORMULAS
# =========================================================

def epley_1rm(w, r):
    return w * (1 + r / 30)

def progression(reps, rpe, weight):
    avg = sum(reps) / len(reps)

    if rpe >= 9:
        return weight * 0.97, "fatigue drop"

    if avg >= 12 and rpe <= 8:
        return weight * 1.02, "progress"

    if avg < 8:
        return weight, "build reps"

    return weight, "maintain"

# =========================================================
# PERIODIZATION (FIXED SAFE)
# =========================================================

def week_index(df):
    if df.empty or "date" not in df.columns:
        return 1

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    if df["date"].isna().all():
        return 1

    return ((df["date"].max() - df["date"].min()).days // 7) + 1

def phase(w):
    return "deload" if w % 4 == 0 else "build"

# =========================================================
# UI
# =========================================================

st.title("Training System")

page = st.sidebar.radio(
    "Menu",
    ["Train", "Dashboard", "PR Tracking", "Heatmap", "Planner"]
)

df = safe_df()

# =========================================================
# TRAIN
# =========================================================

if page == "Train":

    date = st.date_input("Date", datetime.today())
    split = st.radio("Split", ["Upper", "Lower"], horizontal=True)

    exercises = UPPER if split == "Upper" else LOWER
    session = []

    st.subheader(f"Week {week_index(df)} - {phase(week_index(df))}")

    cols = st.columns(3)

    for i, ex in enumerate(exercises):

        with cols[i % 3]:

            st.markdown(f"### {ex}")

            last = next((x for x in reversed(data) if x["exercise"] == ex), None)

            sets = st.number_input(
                "Sets", 0, 6,
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
                "Weight", 0.0, 300.0,
                last["weight"] if last else 20.0,
                key=f"{ex}_w"
            )

            new_w, msg = progression(reps, rpe, weight)

            st.caption(msg)
            st.success(round(new_w, 1))

            session.append({
                "date": date.strftime("%Y-%m-%d"),
                "exercise": ex,
                "muscle": MUSCLE[ex],
                "sets": sets,
                "reps_list": reps,
                "avg_reps": sum(reps) / len(reps),
                "rpe": rpe,
                "weight": weight,
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
# PR TRACKING
# =========================================================

elif page == "PR Tracking":

    if not df.empty:
        df["est_1rm"] = df.apply(lambda x: epley_1rm(x["weight"], x["avg_reps"]), axis=1)

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
        bal = df.groupby("muscle")["volume"].sum()
        st.bar_chart(bal)
    else:
        st.write("No data")

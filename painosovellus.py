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
    res = supabase.table("workouts").select("*").execute()
    return res.data or []

def save_data(session):
    for r in session:
        try:
            supabase.table("workouts").insert(r).execute()
        except Exception as e:
            st.error(f"Save failed: {e}")

data = load_data()

def safe_df():
    if not data:
        return pd.DataFrame(columns=[
            "date","exercise","muscle",
            "sets","reps_list","avg_reps",
            "rpe","weight","volume"
        ])
    return pd.DataFrame(data)

df = safe_df()

# ensure numeric safety
def to_float(x):
    try:
        return float(x)
    except:
        return 0.0

# =========================================================
# EXERCISES (fixed order: biceps before incline press)
# =========================================================

UPPER = [
    "Assisted Pull-Up",
    "Assisted Dip",
    "Chest Supported Machine Row",
    "Seated Bicep Curl",          # FIXED ORDER
    "Dumbbell Incline Press",
    "Dumbbell Shoulder Press",
    "Machine Abs"
]

LOWER = [
        "RDL",
    "Back Squat",
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
# WEIGHT SYSTEM
# =========================================================

def get_step(ex, weight):
    ex_low = ex.lower()

    if "dumbbell" in ex_low or "curl" in ex_low:
        return 1.0 if weight <= 10 else 2.5

    if "squat" in ex_low or "press" in ex_low or "incline" in ex_low:
        return 1.25

    return 2.5


def snap(weight, step):
    weight = float(weight)
    step = float(step)
    return round(round(weight / step) * step, 1)

# =========================================================
# EPLEY 1RM (FIXED)
# =========================================================

def epley_1rm(weight, reps):
    return weight * (1 + reps / 30)

# =========================================================
# CONSISTENCY ACROSS SESSIONS (FIXED)
# =========================================================

def is_consistent(ex):
    df_ex = df[df["exercise"] == ex].sort_values("date")

    if len(df_ex) < 3:
        return False

    last3 = df_ex.tail(3)

    return (
        (last3["avg_reps"] >= 12).all() and
        (last3["rpe"] <= 8).all()
    )

# =========================================================
# PROGRESSION (FIXED + SAFE TYPES)
# =========================================================

def progression(ex, reps, rpe, weight):

    weight = to_float(weight)
    avg = sum(reps) / max(len(reps), 1)
    step = float(get_step(ex, weight))

    consistent = is_consistent(ex)

    # fatigue
    if rpe >= 9:
        return snap(weight * 0.97, step), "fatigue drop"

    # ONLY progress if truly consistent across sessions
    if consistent and avg >= 12 and rpe <= 8:
        return snap(weight + step, step), "progress (consistent)"

    # build reps first
    if avg < 8:
        return weight, "build reps"

    return weight, "maintain"

# =========================================================
# RECOMMENDED WEIGHT (AUTO-FILL FIX)
# =========================================================

def recommended_weight(ex):
    df_ex = df[df["exercise"] == ex]

    if df_ex.empty:
        return 20.0

    last = df_ex.sort_values("date").tail(1).iloc[0]

    est = epley_1rm(last["weight"], last["avg_reps"])
    target_10rm = est / (1 + 10/30)

    step = get_step(ex, last["weight"])
    return snap(target_10rm, step)

# =========================================================
# UI
# =========================================================

st.title("Training System")

page = st.sidebar.radio(
    "Menu",
    ["Train", "Dashboard", "PR Tracking", "Heatmap", "Planner"]
)

# =========================================================
# TRAIN (5 columns fixed + autofill fix)
# =========================================================

if page == "Train":

    date = st.date_input("Date", datetime.today())
    split = st.radio("Split", ["Upper", "Lower"], horizontal=True)

    exercises = UPPER if split == "Upper" else LOWER
    session = []

    st.subheader("Training Session")

    cols = st.columns(5)

    for i, ex in enumerate(exercises):

        with cols[i % 5]:

            st.markdown(f"### {ex}")

            last = next((x for x in reversed(data) if x["exercise"] == ex), None)

            rec_w = recommended_weight(ex)

            sets = st.number_input(
                "Sets", 0, 6,
                int(last["sets"]) if last else 3,
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
                        int(last_reps[i2]) if i2 < len(last_reps) else 10,
                        key=f"{ex}_{i2}"
                    )
                )

            rpe = st.slider("RPE", 1, 10, 8, key=f"{ex}_r")

            weight = st.number_input(
                "Weight (recommended auto)",
                0.0, 300.0,
                float(rec_w),   # FIXED AUTOFILL
                step=0.5,
                key=f"{ex}_w"
            )

            new_w, msg = progression(ex, reps, rpe, weight)

            st.caption(msg)
            st.success(f"Next: {new_w} kg")

            session.append({
                "date": date.strftime("%Y-%m-%d"),
                "exercise": ex,
                "muscle": MUSCLE[ex],
                "sets": sets,
                "reps_list": reps,
                "avg_reps": float(sum(reps) / max(len(reps), 1)),
                "rpe": int(rpe),
                "weight": float(weight),
                "volume": float(sum(reps) * weight)
            })

    if st.button("Save session"):
        save_data(session)
        st.success("Saved")

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
# PR TRACKING (EPLEY FIXED)
# =========================================================

elif page == "PR Tracking":

    if not df.empty:
        df["est_1rm"] = df.apply(
            lambda x: epley_1rm(to_float(x["weight"]), to_float(x["avg_reps"])),
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

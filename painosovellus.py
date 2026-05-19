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

# =========================================================
# HELPERS
# =========================================================

def to_float(x):
    try:
        return float(x)
    except:
        return 0.0


def session_summary(df):
    """Collapse per-day session (IMPORTANT for calendar)"""
    if df.empty:
        return df

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    summary = df.groupby("date").agg({
        "volume": "sum",
        "muscle": lambda x: x.mode()[0] if len(x) else "unknown"
    }).reset_index()

    return summary

# =========================================================
# EXERCISES
# =========================================================

LOWER = [
    "RDL",
    "Back Squat",
    "Bulgarian Split Squat",
    "Leg Extension",
    "Hip Abduction"
]

UPPER = [
    "Assisted Pull-Up",
    "Assisted Dip",
    "Chest Supported Machine Row",
    "Dumbbell Shoulder Press",
    "Seated Bicep Curl",
    "Dumbbell Incline Press",
    "Machine Abs"
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

    if any(x in ex_low for x in ["back squat", "rdl", "bulgarian split squat"]):
        return 2.5

    if "chest supported machine row" in ex_low:
        return 1.25

    if "dumbbell" in ex_low or "curl" in ex_low:
        return 1.0 if weight <= 10 else 2.5

    return 2.5


def snap(weight, step):
    weight = float(weight)
    step = float(step)
    return float(round(round(weight / step) * step, 1))

# =========================================================
# DASHBOARD (NEW CALENDAR VIEW)
# =========================================================

elif page == "Dashboard":

    st.title("📅 Training Calendar View")

    if df.empty:
        st.write("No data")
        st.stop()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    summary = session_summary(df)

    view = st.radio(
        "View",
        ["1 Week", "1 Month", "All"],
        horizontal=True
    )

    now = pd.Timestamp.today()

    if view == "1 Week":
        filtered = summary[summary["date"] >= now - pd.Timedelta(days=7)]
    elif view == "1 Month":
        filtered = summary[summary["date"] >= now - pd.Timedelta(days=30)]
    else:
        filtered = summary

    st.subheader("Calendar Feed")

    for _, row in filtered.sort_values("date", ascending=False).iterrows():

        date = row["date"].date()
        volume = row["volume"]
        muscle = row["muscle"]

        # COLOR RULE (NO MIXED DAYS)
        if muscle == "legs":
            color = "🔵"
            label = "Lower"
        else:
            color = "🟢"
            label = "Upper"

        st.markdown(
            f"""
            ### {color} {date} — {label} Day  
            **Total Volume:** {round(volume, 1)} kg  
            """
        )

    st.divider()

    st.subheader("Volume Trend")

    st.line_chart(summary.set_index("date")["volume"])

    st.subheader("Muscle Distribution")

    st.bar_chart(df.groupby("muscle")["volume"].sum())

# =========================================================
# OTHER PAGES (UNCHANGED BELOW)
# =========================================================

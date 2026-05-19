import streamlit as st
import pandas as pd
import calendar
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
    if df.empty:
        return df

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    return df.groupby("date").agg({
        "volume": "sum",
        "muscle": lambda x: x.mode()[0] if len(x) else "unknown"
    }).reset_index()


def day_meta(summary_df):
    """map date -> volume + upper/lower flag"""
    meta = {}
    for _, r in summary_df.iterrows():
        date = r["date"].date()
        meta[date] = {
            "volume": float(r["volume"]),
            "muscle": r["muscle"]
        }
    return meta

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
# WEIGHT SYSTEM (unchanged)
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
# PROGRESSION (unchanged)
# =========================================================

def progression(ex, reps, rpe, weight):
    weight = float(weight)
    avg = sum(reps) / max(len(reps), 1)
    step = get_step(ex, weight)

    if rpe >= 9:
        return snap(weight * 0.97, step), "fatigue drop"

    if avg >= 12 and rpe <= 8:
        return snap(weight + step, step), "progress"

    if avg < 8:
        return weight, "build reps"

    return weight, "maintain"

# =========================================================
# RECOMMENDED WEIGHT (unchanged)
# =========================================================

def recommended_weight(ex):
    df_ex = df[df["exercise"] == ex]

    if df_ex.empty:
        return 20.0

    last = df_ex.sort_values("date").tail(1).iloc[0]

    est = last["weight"] * (1 + last["avg_reps"] / 30)
    target = est / (1 + 10/30)

    step = get_step(ex, last["weight"])
    return snap(target, step)

# =========================================================
# UI
# =========================================================

st.title("Training System")

page = st.sidebar.radio(
    "Menu",
    ["Train", "Dashboard", "PR Tracking", "Heatmap", "Planner"]
)

# =========================================================
# TRAIN (unchanged)
# =========================================================

if page == "Train":

    date = st.date_input("Date", datetime.today())
    split = st.radio("Split", ["Lower", "Upper"], horizontal=True)

    exercises = LOWER if split == "Lower" else UPPER
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
                "Weight",
                0.0, 300.0,
                float(rec_w),
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
# DASHBOARD (CALENDAR GRID)
# =========================================================

elif page == "Dashboard":

    st.title("Training Calendar")

    if df.empty:
        st.write("No data")
        st.stop()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    summary = session_summary(df)
    meta = day_meta(summary)

    view = st.radio("View", ["1 Week", "1 Month", "All"], horizontal=True)

    # -----------------------------
    # FILTER RANGE
    # -----------------------------
    today = pd.Timestamp.today().date()

    if view == "1 Week":
        start = today - pd.Timedelta(days=7)
        summary = summary[summary["date"] >= start]

    elif view == "1 Month":
        start = today.replace(day=1)
        summary = summary[summary["date"] >= start]

    # -----------------------------
    # ADD WEEKDAY COLUMN
    # -----------------------------
    summary["weekday"] = summary["date"].dt.day_name()

    # enforce correct order Monday → Sunday
    weekday_order = [
        "Monday", "Tuesday", "Wednesday",
        "Thursday", "Friday", "Saturday", "Sunday"
    ]

    cols = st.columns(7)

    # -----------------------------
    # HEADER ROW (FIXED)
    # -----------------------------
    for i, day in enumerate(weekday_order):
        cols[i].markdown(f"### {day}")

    # -----------------------------
    # GROUP DATA BY WEEKDAY
    # -----------------------------
    grouped = {
        d: summary[summary["weekday"] == d].sort_values("date")
        for d in weekday_order
    }

    # -----------------------------
    # FIND MAX ROWS PER COLUMN
    # -----------------------------
    max_len = max(len(v) for v in grouped.values()) if grouped else 0

    # -----------------------------
    # VERTICAL COLUMNS LAYOUT
    # -----------------------------
    for row_idx in range(max_len):

        row_cols = st.columns(7)

        for col_idx, day in enumerate(weekday_order):

            df_day = grouped.get(day)

            if df_day is None or row_idx >= len(df_day):
                row_cols[col_idx].markdown(
                    """
                    <div style="
                        padding:10px;
                        border-radius:8px;
                        background-color:#f3f3f3;
                        text-align:center;
                        min-height:80px;
                    ">
                        -
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                continue

            r = df_day.iloc[row_idx]
            d = r["date"].date()

            vol = r["volume"]
            muscle = r["muscle"]

            label = "Lower" if muscle == "legs" else "Upper"
            color = "#ffdddd" if label == "Lower" else "#dde8ff"

            row_cols[col_idx].markdown(
                f"""
                <div style="
                    background-color:{color};
                    padding:10px;
                    border-radius:8px;
                    text-align:center;
                    min-height:80px;
                ">
                    <div><b>{d.day}/{d.month}</b></div>
                    <div>{label}</div>
                    <div>{round(vol,1)} kg</div>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.divider()

    st.subheader("Volume Trend")
    st.line_chart(summary.set_index("date")["volume"])

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

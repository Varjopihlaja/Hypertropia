import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta
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
    meta = {}
    for _, r in summary_df.iterrows():
        meta[r["date"].date()] = {
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
# ASSISTED LOGIC
# =========================================================

def is_assisted(ex):
    ex = ex.lower()
    return "assisted pull-up" in ex or "assisted dip" in ex

# =========================================================
# PROGRESSION (FIXED)
# =========================================================

def progression(ex, reps, rpe, weight):
    avg = sum(reps) / max(len(reps), 1)
    step = get_step(ex, weight)

    if is_assisted(ex):

        if rpe >= 9:
            return snap(weight + step, step), "more assistance"

        if avg >= 12 and rpe <= 8:
            return snap(weight - step, step), "less assistance"

        if avg < 8:
            return weight, "build reps"

        return weight, "maintain"

    if rpe >= 9:
        return snap(weight * 0.97, step), "fatigue drop"

    if avg >= 12 and rpe <= 8:
        return snap(weight + step, step), "progress"

    if avg < 8:
        return weight, "build reps"

    return weight, "maintain"

# =========================================================
# RECOMMENDED WEIGHT
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
# WEEKLY PLAN (ROLLING AVERAGE)
# =========================================================

def weekly_plan(ex):
    df_ex = df[df["exercise"] == ex].copy()

    if df_ex.empty:
        return "No data"

    df_ex["date"] = pd.to_datetime(df_ex["date"], errors="coerce")
    last7 = df_ex.sort_values("date").tail(7)

    avg_w = last7["weight"].mean()
    avg_r = last7["avg_reps"].mean()

    step = get_step(ex, avg_w)

    if avg_r >= 12:
        return snap(avg_w + step, step)
    elif avg_r < 8:
        return snap(avg_w, step)
    return snap(avg_w, step)

# =========================================================
# UI
# =========================================================

st.title("Training System")

page = st.sidebar.radio(
    "Menu",
    ["Train", "Dashboard", "PR Tracking", "Heatmap", "Planner"]
)

# =========================================================
# TRAIN (compact reps + colors)
# =========================================================

if page == "Train":

    date = st.date_input("Date", datetime.today())
    split = st.radio("Split", ["Lower", "Upper"], horizontal=True)

    exercises = LOWER if split == "Lower" else UPPER
    session = []

    cols = st.columns(5)

    for i, ex in enumerate(exercises):

        with cols[i % 5]:

            st.markdown(
                f"<div style='border:1px solid #ddd;padding:6px;border-radius:10px'>{ex}</div>",
                unsafe_allow_html=True
            )

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

            rep_cols = st.columns(sets)
            for i2 in range(sets):
                with rep_cols[i2]:
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
            st.success(f"Next: {new_w}")

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
# DASHBOARD (FIXED CALENDAR + BORDER + BUFFER DAYS)
# =========================================================

elif page == "Dashboard":

    st.title("Training Calendar")

    if df.empty:
        st.write("No data")
        st.stop()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    summary = session_summary(df)
    meta = day_meta(summary)

    view = st.radio("View", ["1 Week", "1 Month", "Last 3 Months", "All"], horizontal=True)

    today = datetime.today().date()

    if view == "1 Week":
        start = today - timedelta(days=6)
        end = today

    elif view == "1 Month":
        start = today.replace(day=1)
        end = (start + pd.offsets.MonthEnd(1)).date()

    elif view == "Last 3 Months":
        start = (today.replace(day=1) - pd.DateOffset(months=2)).date()
        end = today

    else:
        start = df["date"].min().date()
        end = df["date"].max().date()

    grid_start = start - timedelta(days=start.weekday())
    grid_end = end + timedelta(days=(6 - end.weekday()))
    grid = pd.date_range(grid_start, grid_end)

    weekdays = [
        "Monday", "Tuesday", "Wednesday",
        "Thursday", "Friday", "Saturday", "Sunday"
    ]

    cols = st.columns(7)

    for i in range(7):
        cols[i].markdown(f"**{weekdays[i]}**")

    st.write("")

    for i, d in enumerate(grid):

        col = cols[i % 7]
        day = d.date()

        in_range = start <= day <= end
        in_month = day.month == start.month

        if day in meta and in_range:

            vol = meta[day]["volume"]
            muscle = meta[day]["muscle"]

            label = "Lower" if muscle == "legs" else "Upper"
            bg = "#3b82f6" if label == "Lower" else "#22c55e"

            box = f"""
            <div style="
                background-color:{bg};
                color:white;
                border:2px solid #111;
                border-radius:12px;
                padding:10px;
                min-height:110px;
                text-align:center;
            ">
                <div style="font-size:28px;font-weight:700;">{day.day}</div>
                <div>{label}</div>
                <div>{round(vol,1)} kg</div>
            </div>
            """

        elif in_range and in_month:

            box = f"""
            <div style="
                background-color:#e5e7eb;
                border:2px solid #999;
                border-radius:12px;
                padding:10px;
                min-height:110px;
                text-align:center;
                color:#444;
            ">
                <div style="font-size:28px;font-weight:700;">{day.day}</div>
                <div>Rest</div>
            </div>
            """

        else:

            box = f"""
            <div style="
                background-color:#f9fafb;
                border:1px solid #e5e7eb;
                border-radius:12px;
                padding:10px;
                min-height:110px;
                text-align:center;
                color:#bbb;
            ">
                <div style="font-size:28px;font-weight:700;">{day.day}</div>
            </div>
            """

        col.markdown(box, unsafe_allow_html=True)

    st.line_chart(summary.set_index("date")["volume"])

# =========================================================
# PR TRACKING
# =========================================================

elif page == "PR Tracking":

    if not df.empty:
        df["est_1rm"] = df.apply(
            lambda x: to_float(x["weight"]) * (1 + to_float(x["avg_reps"]) / 30),
            axis=1
        )

        st.subheader("Estimated Strength (1RM)")

        for ex in df["exercise"].unique():
            pr = df[df["exercise"] == ex]["est_1rm"].max()
            st.metric(ex, round(pr, 1))

    else:
        st.write("No data")

# =========================================================
# HEATMAP (VISUAL)
# =========================================================

elif page == "Heatmap":

    if not df.empty:
        st.subheader("Muscle Volume")

        for m in df["muscle"].unique():
            val = df[df["muscle"] == m]["volume"].sum()
            st.metric(m, f"{round(val,1)} kg")

    else:
        st.write("No data")

# =========================================================
# PLANNER (UPPER / LOWER SPLIT + WEEKLY PLAN)
# =========================================================

elif page == "Planner":

    if not df.empty:
        st.subheader("Weekly Plan")

        st.markdown("### Upper Body")
        for ex in UPPER:
            st.write(ex, "→", weekly_plan(ex))

        st.markdown("### Lower Body")
        for ex in LOWER:
            st.write(ex, "→", weekly_plan(ex))

    else:
        st.write("No data")

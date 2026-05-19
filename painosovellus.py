import streamlit as st
import pandas as pd
import numpy as np
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
        supabase.table("workouts").insert(r).execute()

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

def session_summary(df):
    if df.empty:
        return df

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    return df.groupby("date").agg({
        "volume": "sum",
        "muscle": lambda x: x.mode()[0] if len(x) else "unknown"
    }).reset_index()

def weekly_fatigue(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
    return df.groupby(["week", "muscle"])["volume"].sum().reset_index()

def weekly_exercise_volume(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
    return df.groupby(["exercise", "week"])["volume"].sum().reset_index()

def day_meta(summary_df):
    meta = {}
    for _, r in summary_df.iterrows():
        meta[r["date"].date()] = {
            "volume": float(r["volume"]),
            "muscle": r["muscle"]
        }
    return meta

def build_cycles(df):
    """
    Detects Lower / Upper / Rest repeating structure
    based on chronological order of sessions.
    """

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("date")

    # Assign cycle pattern index
    pattern = ["Lower", "Upper", "Rest"]

    cycle_ids = []
    cycle_index = 0

    for i in range(len(df)):
        cycle_ids.append(cycle_index)
        if (i + 1) % 3 == 0:
            cycle_index += 1

    df["cycle"] = cycle_ids
    df["cycle_phase"] = [pattern[i % 3] for i in range(len(df))]

    return df

cycle_df = build_cycles(df)

# =========================================================
# FORECAST (REAL vs NEXT WEEK)
# =========================================================

def forecast(series_df, x_col, y_col):
    df2 = series_df.copy().dropna()
    if len(df2) < 2:
        return df2, None

    df2 = df2.sort_values(x_col)

    x = np.arange(len(df2))
    y = df2[y_col].values

    slope = np.polyfit(x, y, 1)[0]

    future_x = np.arange(len(df2), len(df2) + 7)
    future_y = y[-1] + slope * (future_x - len(df2) + 1)

    future_dates = pd.date_range(df2[x_col].iloc[-1], periods=8, freq="D")[1:]

    future = pd.DataFrame({
        x_col: future_dates,
        y_col: future_y
    })

    return df2, future

# =========================================================
# EXERCISES
# =========================================================

LOWER = ["RDL","Back Squat","Bulgarian Split Squat","Leg Extension","Hip Abduction"]

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
    "Back Squat":"legs","RDL":"legs","Bulgarian Split Squat":"legs",
    "Leg Extension":"legs","Hip Abduction":"glutes",
    "Chest Supported Machine Row":"back","Dumbbell Incline Press":"chest",
    "Dumbbell Shoulder Press":"shoulders","Seated Bicep Curl":"arms",
    "Machine Abs":"core","Assisted Pull-Up":"back","Assisted Dip":"chest"
}

# =========================================================
# PROGRESSION
# =========================================================

def get_step(ex):
    return 1.25 if "machine row" in ex.lower() else 2.5

def snap(w, step):
    return round(round(w / step) * step, 2)

def is_assisted(ex):
    return "assisted pull-up" in ex.lower() or "assisted dip" in ex.lower()

def progression(ex, reps, rpe, weight):
    avg = sum(reps)/max(len(reps),1)
    step = get_step(ex)
    assisted = is_assisted(ex)

    if assisted:
        if rpe >= 9:
            return snap(weight + step, step), "increase assistance"
        if avg >= 12 and rpe <= 8:
            return snap(weight - step, step), "reduce assistance"
        return weight, "maintain"

    if rpe >= 9:
        return snap(weight * 0.97, step), "fatigue drop"
    if avg >= 12:
        return snap(weight + step, step), "progress"
    if avg < 8:
        return weight, "build reps"
    return weight, "maintain"

def recommended_weight(ex):
    df_ex = df[df["exercise"] == ex]
    if df_ex.empty:
        return 20

    last = df_ex.sort_values("date").iloc[-1]
    est = last["weight"] * (1 + last["avg_reps"]/30)
    target = est / (1 + 10/30)

    return snap(target, get_step(ex))

# =========================================================
# UI
# =========================================================

st.title("Training System")

page = st.sidebar.radio(
    "Menu",
    ["Train","Dashboard","1RM Tracking","Muscle Load","Fatigue Planner","Progression"]
)

# =========================================================
# TRAIN
# =========================================================

if page == "Train":
    date = st.date_input("Date", datetime.today())
    split = st.radio("Split", ["Lower","Upper"], horizontal=True)

    exercises = LOWER if split=="Lower" else UPPER
    session = []

    cols = st.columns(5)

    for i, ex in enumerate(exercises):
        with cols[i % 5]:

            st.markdown(f"### {ex}")

            last = next((x for x in reversed(data) if x["exercise"]==ex), None)
            rec_w = recommended_weight(ex)

            sets = st.number_input("Sets",0,6,int(last["sets"]) if last else 3,key=f"{ex}s")

            reps = []
            last_reps = last["reps_list"] if last else [10]*sets

            rep_cols = st.columns(max(1, sets))

            for i2 in range(sets):
                with rep_cols[i2]:
                    reps.append(
                        st.number_input(
                            f"{i2+1}",
                            0,30,
                            int(last_reps[i2]) if i2<len(last_reps) else 10,
                            key=f"{ex}r{i2}"
                        )
                    )

            rpe = st.slider("RPE",1,10,8,key=f"{ex}rpe")
            weight = st.number_input("Weight",0.0,300.0,float(rec_w),step=0.5,key=f"{ex}w")

            new_w,msg = progression(ex,reps,rpe,weight)

            st.caption(msg)
            st.success(f"Next: {new_w}")

            session.append({
                "date":date.strftime("%Y-%m-%d"),
                "exercise":ex,
                "muscle":MUSCLE[ex],
                "sets":sets,
                "reps_list":reps,
                "avg_reps":sum(reps)/max(len(reps),1),
                "rpe":rpe,
                "weight":weight,
                "volume":sum(reps)*weight
            })

    if st.button("Save"):
        save_data(session)
        st.success("Saved")

# =========================================================
# DASHBOARD
# =========================================================

elif page == "Dashboard":
    st.title("Calendar")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    summary = session_summary(df)
    meta = day_meta(summary)

    view = st.radio("View",["Week","Month","3 Months","All"],horizontal=True)

    today = datetime.today().date()

    if view=="Week":
        start = today - timedelta(days=6)
        end = today
    elif view=="Month":
        start = today.replace(day=1)
        end = (start + pd.offsets.MonthEnd(1)).date()
    elif view=="3 Months":
        start = (today.replace(day=1)-pd.DateOffset(months=2)).date()
        end = today
    else:
        start = df["date"].min().date()
        end = df["date"].max().date()

    grid_start = start - timedelta(days=start.weekday())
    grid_end = end + timedelta(days=(6-end.weekday()))
    grid = pd.date_range(grid_start, grid_end)

    cols = st.columns(7)

    for i,d in enumerate(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]):
        cols[i].markdown(f"**{d}**")

    for i,d in enumerate(grid):
        col = cols[i%7]
        day = d.date()

        in_range = start <= day <= end

        if day in meta and in_range:
            vol = meta[day]["volume"]
            label = "Lower" if meta[day]["muscle"]=="legs" else "Upper"
            color = "#2563eb" if label=="Upper" else "#16a34a"

            box = f"""
            <div style="border:1px solid #ccc;border-radius:10px;background:{color};color:white;padding:10px;min-height:90px;text-align:center">
                <div style="font-size:26px">{day.day}</div>
                <div>{label}</div>
                <div>{round(vol,1)} kg</div>
            </div>"""
        else:
            box = f"""
            <div style="border:1px solid #e5e7eb;border-radius:10px;background:#f3f4f6;padding:10px;min-height:90px;text-align:center;color:#9ca3af">
                <div style="font-size:26px">{day.day}</div>
                <div>Rest</div>
            </div>"""

        col.markdown(box,unsafe_allow_html=True)

    st.line_chart(summary.set_index("date")["volume"])

# =========================================================
# 1RM
# =========================================================

elif page == "1RM Tracking":

    df["est"] = df["weight"]*(1+df["avg_reps"]/30)

    left,right = st.columns(2)

    with left:
        st.subheader("Upper")
        for ex in UPPER:
            d=df[df["exercise"]==ex]
            if not d.empty:
                st.write(ex, round(d["est"].max(),1))

    with right:
        st.subheader("Lower")
        for ex in LOWER:
            d=df[df["exercise"]==ex]
            if not d.empty:
                st.write(ex, round(d["est"].max(),1))


# =========================================================
# MUSCLE LOAD
# =========================================================

elif page == "Muscle Load":

    import altair as alt

    st.title("Muscle Load")

    # -------------------------------------------------
    # PREP
    # -------------------------------------------------
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
    df["month"] = df["date"].dt.to_period("M").astype(str)

    view = st.radio("View", ["Week", "Month"], horizontal=True)

    # -------------------------------------------------
    # EXERCISE → MUSCLE MAP
    # -------------------------------------------------
    EX_MAP = {
        "Back Squat": ["quads", "glutes", "core"],
        "RDL": ["hamstrings", "glutes", "back"],
        "Bulgarian Split Squat": ["quads", "glutes"],
        "Leg Extension": ["quads"],
        "Hip Abduction": ["glutes"],
        "Assisted Pull-Up": ["back", "biceps"],
        "Assisted Dip": ["chest", "triceps", "shoulders"],
        "Chest Supported Machine Row": ["back", "biceps"],
        "Dumbbell Shoulder Press": ["shoulders", "triceps"],
        "Seated Bicep Curl": ["biceps"],
        "Dumbbell Incline Press": ["chest", "shoulders", "triceps"],
        "Machine Abs": ["core"]
    }

    ranges = {
        "chest": (10, 20),
        "back": (12, 20),
        "quads": (10, 18),
        "hamstrings": (8, 16),
        "shoulders": (8, 16),
        "biceps": (6, 14),
        "triceps": (6, 14),
        "glutes": (8, 16),
        "core": (8, 12)
    }

    def build_df(input_df):
        rows = []
        for _, r in input_df.iterrows():
            muscles = EX_MAP.get(r["exercise"], [r["muscle"]])
            split_sets = r["sets"] / len(muscles)
            for m in muscles:
                rows.append({"muscle": m, "sets": split_sets})
        return pd.DataFrame(rows).groupby("muscle", as_index=False)["sets"].sum()

    # =========================================================
    # WEEK VIEW
    # =========================================================
    if view == "Week":

        st.subheader("Weekly Load")

        weeks = sorted(df["week"].dropna().unique())
        if len(weeks) == 0:
            st.write("No data")
            st.stop()

        selected_week = st.selectbox(
            "Select week",
            weeks,
            format_func=lambda x: x.strftime("%d.%m.%Y")
        )

        week_df = df[df["week"] == selected_week]
        plot_df = build_df(week_df)

        plot_df = plot_df[plot_df["muscle"].isin(ranges.keys())]

        if plot_df.empty:
            st.write("No data")
            st.stop()

        plot_df["min"] = plot_df["muscle"].map(lambda m: ranges[m][0])
        plot_df["max"] = plot_df["muscle"].map(lambda m: ranges[m][1])

        def status(row):
            if row["sets"] < row["min"]:
                return "below"
            elif row["sets"] > row["max"]:
                return "above"
            return "optimal"

        plot_df["status"] = plot_df.apply(status, axis=1)

        base = alt.Chart(plot_df)

        bars = base.mark_bar(color="#93c5fd").encode(
            x=alt.X("muscle:N"),
            y=alt.Y("sets:Q", scale=alt.Scale(zero=True)),
            color=alt.Color(
                "status:N",
                scale=alt.Scale(
                    domain=["below", "optimal", "above"],
                    range=["#f59e0b", "#22c55e", "#ef4444"]
                )
            ),
            tooltip=["muscle", "sets", "min", "max", "status"]
        )

        # ✅ CORRECT RANGE (true interval, fixed scaling)
        range_bar = base.mark_bar(
            color="black",
            opacity=0.25
        ).encode(
            x="muscle:N",
            y=alt.Y("min:Q"),
            y2="max:Q"
        )

        st.altair_chart(bars + range_bar, use_container_width=True)

        st.markdown("""
**Weekly targets:** Chest 10–20 | Back 12–20 | Quads 10–18 | Hamstrings 8–16 | Shoulders 8–16 | Arms 6–14 | Glutes 8–16 | Core 8–12
""")

    # =========================================================
    # MONTH VIEW (FIXED SCALING)
    # =========================================================
    else:

        st.subheader("Monthly Calendar View")

        months = sorted(df["month"].dropna().unique())
        if len(months) == 0:
            st.write("No data")
            st.stop()

        selected_month = st.selectbox("Select month", months)

        month_df = df[df["month"] == selected_month].copy()
        month_df["date"] = pd.to_datetime(month_df["date"], errors="coerce")
        month_df["week"] = month_df["date"].dt.to_period("W").apply(lambda r: r.start_time)

        if month_df.empty:
            st.write("No data")
            st.stop()

        week_blocks = []
        for w in sorted(month_df["week"].unique()):
            wk = build_df(month_df[month_df["week"] == w])
            wk["week"] = w
            week_blocks.append(wk)

        cal_df = pd.concat(week_blocks)
        cal_df = cal_df[cal_df["muscle"].isin(ranges.keys())]

        cal_df["min"] = cal_df["muscle"].map(lambda m: ranges[m][0])
        cal_df["max"] = cal_df["muscle"].map(lambda m: ranges[m][1])

        def status(row):
            if row["sets"] < row["min"]:
                return "below"
            elif row["sets"] > row["max"]:
                return "above"
            return "optimal"

        cal_df["status"] = cal_df.apply(status, axis=1)

        base = alt.Chart(cal_df)

        bars = base.mark_bar(color="#93c5fd").encode(
            x=alt.X("muscle:N"),
            y=alt.Y("sets:Q", scale=alt.Scale(zero=True)),
            color="status:N",
            tooltip=["week", "muscle", "sets", "min", "max", "status"]
        )

        # ✅ FIXED scaling range bar
        range_bar = base.mark_bar(
            color="black",
            opacity=0.25
        ).encode(
            x="muscle:N",
            y="min:Q",
            y2="max:Q"
        )

        st.altair_chart(bars + range_bar, use_container_width=True)

        st.markdown("""
**Weekly targets:** Chest 10–20 | Back 12–20 | Quads 10–18 | Hamstrings 8–16 | Shoulders 8–16 | Arms 6–14 | Glutes 8–16 | Core 8–12
""")

# =========================================================
# FATIGUE PLANNER
# =========================================================

elif page == "Fatigue Planner":

    st.title("Fatigue Curves with Forecast")

    st.markdown("""
    ### What this shows
    - Solid line = actual weekly training load (fatigue)
    - Dotted line = projected next 7 days trend
    - Used to detect overreaching or undertraining
    """)

    weekly = weekly_fatigue(df)

    if weekly.empty:
        st.write("No data")
        st.stop()

    left,right = st.columns(2)

    for col, muscle_filter, title in [
        (left, "upper", "Upper Body Fatigue"),
        (right, "lower", "Lower Body Fatigue")
    ]:
        pass

    upper = weekly[weekly["muscle"] != "legs"].groupby("week")["volume"].sum().reset_index()
    lower = weekly[weekly["muscle"] == "legs"].groupby("week")["volume"].sum().reset_index()

    hist_u, fut_u = forecast(upper, "week", "volume")
    hist_l, fut_l = forecast(lower, "week", "volume")

    with left:
        st.subheader("Upper Body")
        st.line_chart(hist_u.set_index("week")["volume"])
        if fut_u is not None:
            st.line_chart(fut_u.set_index("week")["volume"])

    with right:
        st.subheader("Lower Body")
        st.line_chart(hist_l.set_index("week")["volume"])
        if fut_l is not None:
            st.line_chart(fut_l.set_index("week")["volume"])

# =========================================================
# PROGRESSION
# =========================================================

elif page == "Progression":

    st.title("Strength Progression vs Forecast")

    weekly = weekly_exercise_volume(df)

    if weekly.empty:
        st.write("No data")
        st.stop()

    split = st.radio("View", ["Upper","Lower"], horizontal=True)
    exercises = UPPER if split=="Upper" else LOWER

    ex = st.selectbox("Exercise", exercises)

    d = weekly[weekly["exercise"]==ex].sort_values("week")

    st.markdown("""
    ### What this shows
    - Blue = actual progression
    - Orange = predicted next trend
    - Helps evaluate overload efficiency
    """)

    hist, future = forecast(d, "week", "volume")

    st.line_chart(hist.set_index("week")["volume"])

    if future is not None:
        st.line_chart(future.set_index("week")["volume"])

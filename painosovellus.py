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
# COACH MODE SETTINGS
# =========================================================

COACH_MODE = "hypertrophy"

def get_target_reps():
    return (4, 8) if COACH_MODE == "strength" else (8, 12)

def get_progression_step(ex):
    return 1.25 if "machine row" in ex.lower() else 2.5

# =========================================================
# HELPERS
# =========================================================

def valid_lifts(df):
    if df.empty:
        return df

    df = df.copy()
    df["sets"] = pd.to_numeric(df["sets"], errors="coerce").fillna(0)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)

    return df[(df["sets"] > 0) & (df["volume"] > 0)]

def normalize_date(x):
    return pd.to_datetime(x, errors="coerce").date()

def fmt_date(d):
    return pd.to_datetime(d, errors="coerce").strftime("%d.%m.%Y")

def session_summary(df):
    if df.empty:
        return df

    df = valid_lifts(df.copy())
    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)

    return df.groupby("date").agg({
        "volume": "sum",
        "muscle": lambda x: x.mode()[0] if len(x) else "unknown"
    }).reset_index()

def day_meta(summary_df):
    meta = {}
    for _, r in summary_df.iterrows():
        meta[r["date"]] = {
            "volume": float(r["volume"]),
            "muscle": r["muscle"]
        }
    return meta

def get_sessions_by_date(date):
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce", dayfirst=True)
    return d[d["date"].dt.date == date]

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
        payload = dict(r)

        # date fix
        payload["date"] = pd.to_datetime(payload["date"]).strftime("%Y-%m-%d")

        # reps safety
        payload["reps_list"] = [int(x) for x in payload.get("reps_list", []) if x is not None]

        # clean numpy + NaN
        for k, v in list(payload.items()):
            if isinstance(v, (np.floating, np.integer)):
                payload[k] = v.item()
            if isinstance(v, (float, int)) and pd.isna(v):
                payload[k] = None

        # ❌ REMOVED: performed / skipped logic

        supabase.table("workouts").insert(payload).execute()

data = load_data()

def safe_df():
    if not data:
        return pd.DataFrame(columns=[
            "date","exercise","muscle","sets",
            "reps_list","avg_reps","rpe","weight","volume"
        ])
    return pd.DataFrame(data)

df = safe_df()

# =========================================================
# EXERCISES
# =========================================================

LOWER = [
    "RDL",
    "Back Squat",
    "Bulgarian Split Squat",
    "Leg Extension",
    "Back Extension",
    "Hip Abduction"
]

UPPER = [
    "Assisted Pull-Up","Assisted Dip","Chest Supported Machine Row",
    "Dumbbell Shoulder Press","Seated Bicep Curl",
    "Dumbbell Incline Press","Machine Abs"
]

MUSCLE = {
    "Back Squat":"legs","RDL":"legs","Bulgarian Split Squat":"legs",
    "Leg Extension":"legs","Back Extension":"glutes","Hip Abduction":"glutes",
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
    reps = list(map(int, reps))

    if len(reps) == 0 or sum(reps) == 0:
        return weight, "no work"

    avg = sum(reps)/len(reps)
    step = get_step(ex)

    if is_assisted(ex):
        # NOTE:
        # higher weight = MORE assistance = easier
    
        if rpe >= 9:
            return snap(weight + step, step), "increase assistance (easier)"
    
        if avg >= 12 and rpe <= 8:
            return snap(weight - step, step), "reduce assistance (harder)"
    
        return weight, "maintain"

            # ONLY progress if consistent high reps
    if avg >= 12 and rpe <= 8:
        return snap(weight + step, step), "progress"
        
        # only reduce if clearly failing
    if avg < 8 or rpe >= 9:
        return snap(weight - step, step), "regress"
        
    return weight, "maintain"
    if avg < 8:
        return weight, "build reps"

    return weight, "maintain"

def recommended_weight(ex):
    d = valid_lifts(df[df["exercise"] == ex].copy())
    if d.empty:
        return 20

    d = d.sort_values("date")

    # last actual session weight (TRUE anchor)
    last_weight = float(d.iloc[-1]["weight"])

    # only allow progression if recent performance supports it
    recent = d.tail(3)

    avg_reps = recent["avg_reps"].mean()

    step = get_progression_step(ex)

    # NO PROGRESSION UNLESS CONSISTENT 12+
    if avg_reps >= 12:
        return snap(last_weight + step, step)

    # slight regression if consistently low
    if avg_reps < 8:
        return snap(last_weight - step, step)

    # otherwise KEEP EXACT previous session
    return last_weight

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

            last = next((x for x in reversed(data)
                         if x["exercise"] == ex and x.get("sets",0)>0), None)

            rec_w = recommended_weight(ex)

            #sets = st.number_input("Sets",0,6,int(last["sets"]) if last else 3,key=f"{ex}s")
            # Sets
            if ex == "Hip Abduction":
                sets = 0
                reps = []
                st.caption("Currently not performed")
            else:
                sets = st.number_input(
                    "Sets",
                    min_value=0,
                    max_value=6,
                    value=int(last["sets"]) if last else 3,
                    step=1,
                    key=f"sets_{ex}"
                )

                # Last logged reps
                last_reps = []
                last_df = valid_lifts(df[df["exercise"] == ex])
            
                if not last_df.empty:
                    last_reps = last_df.sort_values("date").iloc[-1]["reps_list"]
            
                # Keep reps in one row
                reps = []
            
                if sets > 0:
                    rep_cols = st.columns(int(sets))
            
                    for i2 in range(int(sets)):
            
                        default_rep = (
                            int(last_reps[i2])
                            if i2 < len(last_reps)
                            else (int(last_reps[-1]) if last_reps else 10)
                        )
            
                        with rep_cols[i2]:
                            reps.append(
                                st.number_input(
                                    f"Set {i2+1}",
                                    min_value=0,
                                    max_value=30,
                                    value=default_rep,
                                    step=1,
                                    key=f"{ex}_rep_{i2}"
                                )
                            )
        
        

            rpe = st.slider("RPE",1,10,8,key=f"{ex}rpe")
            weight = st.number_input("Weight",0.0,300.0,float(rec_w),step=0.5,key=f"{ex}w")

            new_w,msg = progression(ex,reps,rpe,weight)

            st.caption(msg)
            st.success(f"Next: {new_w}")

            vol =  sum(reps) * weight if reps else 0
            session.append({
                "date": date.strftime("%Y-%m-%d"),
                "exercise": ex,
                "muscle": MUSCLE[ex],
                "sets": sets,
                "reps_list": reps,
                "avg_reps": np.mean(reps) if reps else 0,
                "rpe": rpe,
                "weight": weight,
                "volume": vol
            })

    if st.button("Save"):
        save_data(session)
        st.success("Saved")


# =========================================================
# DASHBOARD
# =========================================================
elif page == "Dashboard":
    st.title("Calendar")

    if "selected_day" not in st.session_state:
        st.session_state.selected_day = None

    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True).dt.date
    summary = session_summary(df.copy())
    summary["date"] = pd.to_datetime(summary["date"], errors="coerce").dt.date
    meta = day_meta(summary)


    view = st.radio(
    "View",
    ["Week", "Last Week", "Month", "3 Months", "All"],
    horizontal=True
)

    today = datetime.today().date()

    # =========================
    # TIME WINDOWS
    # =========================

    if view == "Week":
    # Current calendar week (Mon-Sun)
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)

    elif view == "Last Week":
        # Previous calendar week (Mon-Sun)
        this_monday = today - timedelta(days=today.weekday())
        start = this_monday - timedelta(days=7)
        end = start + timedelta(days=6)
    

    elif view == "Month":
        start = today.replace(day=1)
        end = (pd.Timestamp(start) + pd.offsets.MonthEnd(1)).date()

    elif view == "3 Months":
        start = (today.replace(day=1) - pd.DateOffset(months=2)).date()
        end = today

    else:
        df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)

        valid_dates = df["date"].dropna()
        
        if valid_dates.empty:
            st.info("No training data yet.")
            st.stop()
        
        start = valid_dates.min().date()
        end = valid_dates.max().date()

    # =========================
    # MONTH TITLE (MONTH VIEW ONLY)
    # =========================
    if view == "Month":
        st.subheader(start.strftime("%B %Y"))

    # =========================
    # STYLE (BIGGER TEXT FIX)
    # =========================
    HEIGHT = "160px"

    rest_color = "#e5e7eb"
    out_color = "#ffffff"
    border = "#d1d5db"
    text_rest = "#6b7280"
    text_out = "#9ca3af"

    weekday_names = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

    def render_box(day, color, label, vol, text_color, opacity=1.0):
        return f"""
        <div style="
            background:{color};
            border:1px solid {border};
            padding:10px;
            border-radius:12px;
            color:{text_color};
            text-align:center;
            height:{HEIGHT};
            display:flex;
            flex-direction:column;
            justify-content:space-between;
            opacity:{opacity};
            font-family: sans-serif;
        ">
            <div style="font-size:28px; font-weight:700;">{day.day}</div>
            <div style="font-size:16px; font-weight:500;">{label}</div>
            <div style="font-size:14px; opacity:0.9;">{vol}</div>
        </div>
        """

    # =========================
    # CALENDAR RENDER
    # =========================
    def render_calendar(grid, start, end, meta, cols, key_prefix):

        for i, d in enumerate(grid):
            col = cols[i % 7]
            day = d.date()

            in_range = start <= day <= end
            is_training = day in meta

            color = out_color
            label = ""
            vol = ""
            text_color = text_out
            opacity = 1.0

            # =========================
            # SPILLOVER DAYS (FIXED + FADE)
            # =========================
            if not in_range:
                if is_training:
                    vol = meta[day]["volume"]
                    label = "Lower" if meta[day]["muscle"] == "legs" else "Upper"
                    color = "#16a34a" if label == "Lower" else "#2563eb"
                    text_color = "white"
                    opacity = 0.35
                else:
                    color = "#ffffff"
                    label = ""
                    vol = ""
                    text_color = "#d1d5db"
                    opacity = 0.35

            elif in_range and not is_training:
                color = rest_color
                label = "Rest"
                vol = 0
                text_color = text_rest

            elif is_training:
                vol = meta[day]["volume"]
                label = "Lower" if meta[day]["muscle"] == "legs" else "Upper"
                color = "#16a34a" if label == "Lower" else "#2563eb"
                text_color = "white"

            with col:
                st.markdown(
                    render_box(day, color, label, vol, text_color, opacity),
                    unsafe_allow_html=True
                )

                btn_key = f"{key_prefix}_{day}"

                clicked = st.button("View", key=btn_key)

                if clicked:
                    if st.session_state.selected_day == day:
                        st.session_state.selected_day = None
                    else:
                        st.session_state.selected_day = day

    # =========================
    # GRID SETUP
    # =========================
    grid_start = start - timedelta(days=start.weekday())
    grid_end = end + timedelta(days=(6 - end.weekday()))
    grid = pd.date_range(grid_start, grid_end)

    cols = st.columns(7)

    for i, name in enumerate(weekday_names):
        cols[i].markdown(
            f"<h4 style='text-align:center'>{name}</h4>",
            unsafe_allow_html=True
        )

    # =========================
    # 3 MONTH VIEW (FIXED SEPARATION)
    # =========================
    if view == "3 Months":

        months = pd.period_range(
            start=pd.to_datetime(start),
            end=pd.to_datetime(end),
            freq="M"
        )

        for m in months:
            m_start = m.start_time.date()
            m_end = m.end_time.date()

            # 🔥 MONTH TITLE ABOVE EACH GRID BLOCK
            st.markdown(f"## {m_start.strftime('%B %Y')}")
            st.markdown("---")

            mg_start = m_start - timedelta(days=m_start.weekday())
            mg_end = m_end + timedelta(days=(6 - m_end.weekday()))
            m_grid = pd.date_range(mg_start, mg_end)

            render_calendar(
                m_grid,
                m_start,
                m_end,
                meta,
                cols,
                key_prefix=f"3m_{m_start}"
            )

            st.markdown("<br>", unsafe_allow_html=True)

    else:
        render_calendar(
            grid,
            start,
            end,
            meta,
            cols,
            key_prefix=f"{view}"
        )

    # =========================
    # SESSION DETAIL PANEL
    # =========================
    if st.session_state.selected_day:

        st.divider()
        st.subheader(f"Sessions on {fmt_date(st.session_state.selected_day)}")

        sessions = get_sessions_by_date(st.session_state.selected_day)

        if sessions.empty:
            st.info("No sessions logged.")
        else:
            edited = []

            for i, row in sessions.iterrows():
                st.markdown(f"### {row['exercise']}")

                weight = st.number_input("Weight", value=float(row["weight"]), key=f"w{i}")
                sets = st.number_input("Sets", value=int(row["sets"]), key=f"s{i}")

                reps_list = row["reps_list"]
                new_reps = []

                cols2 = st.columns(max(1, len(reps_list)))

                for j, r in enumerate(reps_list):
                    with cols2[j]:
                        new_reps.append(
                            st.number_input(f"R{j+1}", value=int(r), key=f"r{i}{j}")
                        )

                rpe = st.slider("RPE", 1, 10, int(row["rpe"]), key=f"rpe{i}")

                edited.append({
                    "id": row.get("id"),
                    "date": str(st.session_state.selected_day),
                    "exercise": row["exercise"],
                    "muscle": row["muscle"],
                    "sets": sets,
                    "reps_list": new_reps,
                    "avg_reps": sum(new_reps)/max(len(new_reps),1),
                    "rpe": rpe,
                    "weight": weight,
                    "volume": sum(new_reps)*weight
                })

            if st.button("Save edits"):
                for r in edited:
                    supabase.table("workouts") \
                        .update({
                            "date": r["date"],
                            "exercise": r["exercise"],
                            "muscle": r["muscle"],
                            "sets": int(r["sets"]),
                            "reps_list": [int(x) for x in r["reps_list"]],
                            "avg_reps": float(r["avg_reps"]),
                            "rpe": int(r["rpe"]),
                            "weight": float(r["weight"]),
                            "volume": float(r["volume"])
                        }) \
                        .eq("id", r["id"]) \
                        .execute()

                st.success("Updated!")
                st.rerun()

    st.line_chart(summary.set_index("date")["volume"])
# =========================================================
# 1RM TRACKING
# =========================================================

elif page == "1RM Tracking":

    df["est"] = df["weight"] * (1 + df["avg_reps"] / 30)

    left, right = st.columns(2)

    with left:
        st.subheader("Upper")
        for ex in UPPER:
            d = df[df["exercise"] == ex]
            if not d.empty:
                st.write(ex, round(d["est"].max(), 1))

    with right:
        st.subheader("Lower")
        for ex in LOWER:
            d = df[df["exercise"] == ex]
            if not d.empty:
                st.write(ex, round(d["est"].max(), 1))

# =========================================================
# MUSCLE LOAD
# =========================================================

elif page == "Muscle Load":

    import altair as alt

    st.title("Muscle Load")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    view = st.radio("View", ["Week", "Month"], horizontal=True)

    EX_MAP = {
        "Back Squat": ["quads","glutes","core"],
        "RDL": ["hamstrings","glutes","back"],
        "Bulgarian Split Squat": ["quads","glutes"],
        "Back Extension": ["glutes","hamstrings","back"],
        "Leg Extension": ["quads"],
        "Hip Abduction": ["glutes"],
        "Assisted Pull-Up": ["back","biceps"],
        "Assisted Dip": ["chest","triceps","shoulders"],
        "Chest Supported Machine Row": ["back","biceps"],
        "Dumbbell Shoulder Press": ["shoulders","triceps"],
        "Seated Bicep Curl": ["biceps"],
        "Dumbbell Incline Press": ["chest","shoulders","triceps"],
        "Machine Abs": ["core"]
    }

    ranges = {
        "chest": (10,20),
        "back": (12,20),
        "quads": (10,18),
        "hamstrings": (8,16),
        "shoulders": (8,16),
        "biceps": (6,14),
        "triceps": (6,14),
        "glutes": (8,16),
        "core": (8,12)
    }

    color_scale = alt.Scale(
        domain=["below", "optimal", "above"],
        range=["#f59e0b", "#22c55e", "#ef4444"]
    )

    # =========================================================
    # SAFE BUILD FUNCTION (FIXED KEYERROR)
    # =========================================================
    def build_df(in_df):
        rows = []

        for _, r in in_df.iterrows():
            muscles = EX_MAP.get(r["exercise"], [r["muscle"]])
            split = r["sets"] / len(muscles)

            for m in muscles:
                rows.append({"muscle": m, "sets": split})

        # IMPORTANT FIX: avoid empty DataFrame crash
        if not rows:
            return pd.DataFrame(columns=["muscle", "sets"])

        return (
            pd.DataFrame(rows)
            .groupby("muscle", as_index=False)["sets"]
            .sum()
        )

    # =========================================================
    # CHART BUILDER
    # =========================================================
    def prepare_plot(plot_df):
        if plot_df is None or plot_df.empty:
            return None

        plot_df = plot_df[plot_df["muscle"].isin(ranges.keys())]

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

        bars = base.mark_bar().encode(
            x=alt.X("muscle:N", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("sets:Q", scale=alt.Scale(zero=True)),
            color=alt.Color("status:N", scale=color_scale),
            tooltip=["muscle","sets","min","max","status"]
        )

        range_bar = base.mark_bar(
            color="black",
            opacity=0.25
        ).encode(
            x="muscle:N",
            y="min:Q",
            y2="max:Q"
        )

        return (bars + range_bar).properties(height=180)

    # =========================================================
    # WEEK VIEW (UNCHANGED)
    # =========================================================
    if view == "Week":

        df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
        weeks = sorted(df["week"].dropna().unique(), reverse=True)

        if not weeks:
            st.stop()

        selected_week = st.selectbox(
            "Select week",
            weeks,
            format_func=lambda x: x.strftime("%d.%m.%Y")
        )

        week_df = df[df["week"] == selected_week]
        plot_df = build_df(week_df)

        chart = prepare_plot(plot_df)

        if chart:
            st.altair_chart(chart, use_container_width=True)

    # =========================================================
    # MONTH VIEW (STACKED FULL WEEK ROWS — FIXED)
    # =========================================================
    else:

        months = sorted(df["date"].dt.to_period("M").astype(str).unique())
        selected_month = st.selectbox("Select month", months)

        start = pd.to_datetime(selected_month + "-01")
        end = start + pd.offsets.MonthEnd(1)

        # Align to full Mon–Sun weeks
        grid_start = start - pd.Timedelta(days=start.weekday())
        grid_end = end + pd.Timedelta(days=(6 - end.weekday()))

        all_days = pd.date_range(grid_start, grid_end)

        # split into full week rows (7 days each)
        weeks = [all_days[i:i+7] for i in range(0, len(all_days), 7)]

        st.subheader(start.strftime("%B %Y"))

        for w in weeks:

            week_start = w[0]
            week_end = w[-1]

            # readable label like 27.4 – 3.5
            label = f"{week_start.day}.{week_start.month} – {week_end.day}.{week_end.month}"
            st.markdown(f"### {label}")

            week_df = df[(df["date"] >= week_start) & (df["date"] <= week_end)]
            plot_df = build_df(week_df)

            chart = prepare_plot(plot_df)

            if chart:
                st.altair_chart(chart, use_container_width=True)
            else:
                st.write("No data")

            st.divider()
# =========================================================
# FATIGUE + PROGRESSION (unchanged)
# =========================================================

elif page == "Fatigue Planner":
    st.title("Fatigue Monitor")

    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)

    st.markdown("""
    **Acute load** = last 7 days training stress (what you did recently)  
    **Chronic load** = last 28 days training baseline (your normal capacity)  
    → Fatigue = how much recent work deviates from your baseline
    """)

    view = st.selectbox("Time window", ["1 Week", "1 Month", "All Time"])

    # =========================
    # FILTER WINDOW
    # =========================
    if view == "1 Week":
        cutoff = pd.Timestamp.today() - pd.Timedelta(days=7)
    elif view == "1 Month":
        cutoff = pd.Timestamp.today() - pd.Timedelta(days=30)
    else:
        cutoff = df["date"].min()

    d = df[df["date"] >= cutoff].copy()

    if d.empty:
        st.warning("No data in this period.")
        st.stop()

    # =========================
    # DAILY LOAD
    # =========================
    daily = d.groupby(["date", "muscle"])["volume"].sum().reset_index()
    daily = daily.sort_values("date")

    def rolling_mean(x, w):
        return x.rolling(w, min_periods=1).mean()

    daily["acute"] = daily.groupby("muscle")["volume"].transform(lambda x: rolling_mean(x, 7))
    daily["chronic"] = daily.groupby("muscle")["volume"].transform(lambda x: rolling_mean(x, 28))

    daily["fatigue_index"] = daily["acute"] / daily["chronic"].replace(0, np.nan)
    daily["fatigue_index"] = daily["fatigue_index"].fillna(1.0)

    # =========================
    # ZONES
    # =========================
    def zone(x):
        if x < 0.8:
            return "under"
        elif x <= 1.3:
            return "optimal"
        elif x <= 1.6:
            return "high"
        return "overload"

    daily["zone"] = daily["fatigue_index"].apply(zone)

    latest = daily.iloc[-1]

    col1, col2, col3 = st.columns(3)
    col1.metric("Acute Load", round(latest["acute"], 1))
    col2.metric("Chronic Load", round(latest["chronic"], 1))
    col3.metric("Fatigue Index", round(latest["fatigue_index"], 2))

    if latest["fatigue_index"] > 1.6:
        st.error("High fatigue — deload recommended")
    elif latest["fatigue_index"] > 1.3:
        st.warning("Elevated fatigue — monitor recovery")
    elif latest["fatigue_index"] < 0.8:
        st.info("Low training stimulus")

    # =========================
    # VISUALIZATION (BETTER)
    # =========================
    import altair as alt

    base = alt.Chart(daily).encode(
        x=alt.X("date:T", axis=alt.Axis(format="%d.%m"))
    )

    # Fatigue line per muscle
    fatigue_line = base.mark_line(point=True).encode(
        y=alt.Y("fatigue_index:Q", title="Fatigue Index"),
        color=alt.Color("muscle:N", title="Muscle"),
        tooltip=["date", "muscle", "fatigue_index", "acute", "chronic"]
    )

    # Reference zone lines
    zones = pd.DataFrame({
        "y": [0.8, 1.3, 1.6],
        "label": ["Under", "Optimal", "High"]
    })

    zone_lines = alt.Chart(zones).mark_rule(strokeDash=[6, 6]).encode(
        y="y:Q"
    )

    st.altair_chart(fatigue_line + zone_lines, use_container_width=True)

    st.markdown("""
    ### Interpretation
    - **Acute load** → recent stress (fatigue today)  
    - **Chronic load** → long-term capacity (fitness baseline)  
    - **Fatigue index > 1.3** → accumulating fatigue  
    - **< 0.8** → undertraining / underload  
    """)

#################################################
# PROGRESSION
#################################################

elif page == "Progression":
    st.title("Strength Progression Intelligence")

    import altair as alt

    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)

    # =========================
    # UI CONTROLS
    # =========================
    split = st.radio("View", ["Last 30 Days", "All Time"], horizontal=True)
    ex = st.selectbox("Select exercise", sorted(UPPER + LOWER))

    # =========================
    # HELPERS
    # =========================
    def format_date(d):
        return d.strftime("%d.%m.%Y")

    def build_series(ex):
        d = valid_lifts(df[df["exercise"] == ex].copy())
        if d.empty:
            return None
        d = d[(d["sets"] > 0) & (d["volume"] > 0)]    

        d = d.sort_values("date")

        # filter window
        if split == "Last 30 Days":
            cutoff = pd.Timestamp.today() - pd.Timedelta(days=30)
            d = d[d["date"] >= cutoff]

        if len(d) < 2:
            return None

        # core signals (keep consistent with your system)
        d = d[d["sets"] > 0]
        d["signal"] = d["weight"] * d["avg_reps"]
        d["e1rm"] = d["weight"] * (1 + d["avg_reps"] / 30)
        d["fatigue"] = d["signal"] / (1 + d["rpe"] / 10)

        # smooth trend (visual stability)
        d["trend"] = d["signal"].rolling(3, min_periods=1).mean()

        # overload projection (linear regression)
        x = np.arange(len(d))
        slope = np.polyfit(x, d["signal"], 1)[0]
        d["projection"] = d["signal"].iloc[0] + slope * x

        return d

    d = build_series(ex)

    if d is None:
        st.warning("Not enough data for this exercise.")
        st.stop()

    # =========================
    # METRICS
    # =========================
    last = d.iloc[-1]

    pr_idx = d["signal"].idxmax()
    pr = d.loc[pr_idx, "signal"]
    pr_date = d.loc[pr_idx, "date"]

    x = np.arange(len(d))
    slope = np.polyfit(x, d["signal"], 1)[0] if len(d) > 1 else 0

    plateau_score = d["signal"].diff().abs().rolling(5, min_periods=1).mean().iloc[-1]

    deload_flag = (slope < 0) and (plateau_score < d["signal"].mean() * 0.05)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Current Strength", round(last["signal"], 1))
    col2.metric("Estimated 1RM", round(last["e1rm"], 1))
    col3.metric("Trend Slope", round(slope, 3))
    col4.metric("PR", f"{round(pr,1)} ({format_date(pr_date)})")

    if deload_flag:
        st.warning("⚠️ Possible stagnation detected — consider a deload week.")

    # =========================
    # CHART
    # =========================
    base = alt.Chart(d).encode(
        x=alt.X("date:T", axis=alt.Axis(labelAngle=-45, format="%d.%m.%Y"))
    )

    actual = base.mark_line(color="blue", strokeWidth=2).encode(
        y="signal:Q",
        tooltip=[
            alt.Tooltip("date:T", title="Date"),
            alt.Tooltip("signal:Q", title="Load"),
            alt.Tooltip("rpe:Q", title="RPE")
        ]
    )

    projected = base.mark_line(
        color="red",
        strokeWidth=2,
        strokeDash=[6, 4]
    ).encode(
        y="projection:Q"
    )

    e1rm_line = base.mark_line(color="green", strokeWidth=2, opacity=0.6).encode(
        y="e1rm:Q"
    )

    pr_point = alt.Chart(d[d["signal"] == pr]).mark_point(
        color="gold",
        size=120
    ).encode(
        x="date:T",
        y="signal:Q"
    )

    st.subheader(ex)
    st.altair_chart(actual + projected + e1rm_line + pr_point, use_container_width=True)

    # =========================
    # INSIGHTS
    # =========================
    st.markdown("### Training Insight")

    if slope > 0.1:
        st.success("Progressing well — strong overload trend.")
    elif slope > 0:
        st.info("Slow progression — consider small load increases.")
    else:
        st.error("Downward trend — recovery or deload may be needed.")

    if plateau_score < d["signal"].mean() * 0.03:
        st.warning("Plateau detected — very low variation in performance.")

# =========================
# NEXT SESSION RECOMMENDATION (FIXED LOGIC)
# =========================

if page == "Progression" and d is not None and not d.empty:

    def get_step(ex):
        return 1.25 if "machine row" in ex.lower() else 2.5

    last = d.iloc[-1]

    step = get_step(ex)

    last_weight = float(last["weight"])
    last_reps = float(last["avg_reps"])
    last_rpe = float(last["rpe"])

    # target zone (hypertrophy logic)
    target_low = 8
    target_high = 12

    next_weight = last_weight

    # RULE 1: too easy → increase weight
    if last_reps > target_high and last_rpe <= 8:
        next_weight += step

    # RULE 2: too hard → decrease weight
    elif last_reps < target_low or last_rpe >= 9:
        next_weight -= step

    # RULE 3: perfect zone → small progression
    else:
        next_weight += step * 0.5

    # safety clamp (prevents weird drift)
    next_weight = max(1.0, round(next_weight, 1))

    st.markdown("### Suggested Next Session")
    st.write(f"Recommended weight: **{next_weight:.1f} kg**")
    st.write("Target: 8–12 reps @ RPE 7–9")

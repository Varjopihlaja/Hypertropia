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
    if COACH_MODE == "strength":
        return (4, 8)
    return (8, 12)

def get_progression_step(ex):
    return 1.25 if "machine row" in ex.lower() else 2.5

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

def day_meta(summary_df):
    meta = {}
    for _, r in summary_df.iterrows():
        meta[r["date"].date()] = {
            "volume": float(r["volume"]),
            "muscle": r["muscle"]
        }
    return meta

def get_sessions_by_date(date):
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    return d[d["date"].dt.date == date]

# =========================================================
# UI
# =========================================================

st.title("Training System")

page = st.sidebar.radio(
    "Menu",
    ["Train","Dashboard","1RM Tracking","Muscle Load","Fatigue Planner","Progression"]
)

# =========================================================
# DASHBOARD (FIXED)
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

    if "selected_day" not in st.session_state:
        st.session_state.selected_day = None

    for i,d in enumerate(grid):
        col = cols[i%7]
        day = d.date()

        in_range = start <= day <= end

        if day in meta and in_range:
            vol = meta[day]["volume"]
            label = "Upper" if meta[day]["muscle"]!="legs" else "Lower"
            color = "#2563eb" if label=="Upper" else "#16a34a"

            box = f"""
            <div style="
                border:1px solid #ccc;
                border-radius:10px;
                background:{color};
                color:white;
                padding:10px;
                height:120px;
                display:flex;
                flex-direction:column;
                justify-content:space-between;
                text-align:center;
                overflow:hidden;
            ">
                <div style="font-size:24px;font-weight:600">{day.day}</div>
                <div>{label}</div>
                <div>{round(vol,1)} kg</div>
            </div>
            """
        else:
            box = f"""
            <div style="
                border:1px solid #e5e7eb;
                border-radius:10px;
                background:#f3f4f6;
                padding:10px;
                height:120px;
                display:flex;
                flex-direction:column;
                justify-content:space-between;
                text-align:center;
                color:#9ca3af;
            ">
                <div style="font-size:24px;font-weight:600">{day.day}</div>
                <div>Rest</div>
                <div></div>
            </div>
            """

        if col.button(str(day), key=str(day)):
            st.session_state.selected_day = day

        col.markdown(box, unsafe_allow_html=True)

    # =====================================================
    # SESSION EDITOR (NEW)
    # =====================================================

    if st.session_state.selected_day:
        st.subheader(f"Sessions on {st.session_state.selected_day}")

        sessions = get_sessions_by_date(st.session_state.selected_day)

        if sessions.empty:
            st.info("No sessions logged.")
        else:
            edited = []

            for i, row in sessions.iterrows():
                st.markdown(f"### {row['exercise']}")

                weight = st.number_input(
                    "Weight", value=float(row["weight"]), key=f"w_{i}"
                )

                sets = st.number_input(
                    "Sets", value=int(row["sets"]), key=f"s_{i}"
                )

                reps_list = row["reps_list"]
                new_reps = []

                cols2 = st.columns(len(reps_list))

                for j, r in enumerate(reps_list):
                    with cols2[j]:
                        new_reps.append(
                            st.number_input(
                                f"R{j+1}",
                                value=int(r),
                                key=f"r_{i}_{j}"
                            )
                        )

                edited.append({
                    "id": row.get("id"),
                    "date": row["date"],
                    "exercise": row["exercise"],
                    "muscle": row["muscle"],
                    "sets": sets,
                    "reps_list": new_reps,
                    "avg_reps": sum(new_reps)/len(new_reps),
                    "rpe": row["rpe"],
                    "weight": weight,
                    "volume": sum(new_reps)*weight
                })

            if st.button("Save edits"):
                for r in edited:
                    supabase.table("workouts") \
                        .update(r) \
                        .eq("id", r["id"]) \
                        .execute()

                st.success("Updated!")
                st.rerun()

    st.line_chart(summary.set_index("date")["volume"])

import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime

# ---------------- CONFIG ---------------- #

SUPABASE_URL = "YOUR_URL"
SUPABASE_KEY = "YOUR_KEY"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- AUTH ---------------- #

def login_ui():
    st.title("🔐 Login")

    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    with tab1:
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            if res.user:
                st.session_state.user = res.user
                st.success("Logged in!")
                st.rerun()
            else:
                st.error("Login failed")

    with tab2:
        email = st.text_input("New Email")
        password = st.text_input("New Password", type="password")

        if st.button("Create Account"):
            res = supabase.auth.sign_up({
                "email": email,
                "password": password
            })
            if res.user:
                st.success("Account created! You can log in.")
            else:
                st.error("Signup failed")

# ---------------- PROGRESSION ---------------- #

def suggest(weight, reps, rpe):
    if reps >= 12 and rpe <= 7:
        return round(weight * 1.07, 1), "increase++"
    elif reps >= 12:
        return round(weight * 1.05, 1), "increase"
    elif reps < 8 and rpe >= 9:
        return round(weight * 0.93, 1), "deload"
    return weight, "maintain"

# ---------------- MAIN APP ---------------- #

def app():
    st.title("🏋️ Hypertrophy App")

    user = st.session_state.user
    user_id = user.id

    day = st.selectbox("Workout", ["Upper", "Lower"])

    exercises = {
        "Upper": ["Pull-Up", "Dip", "Row", "Shoulder Press", "Bicep Curl", "Incline Press", "Abs"],
        "Lower": ["RDL", "Squat", "Bulgarian Split Squat", "Leg Extension"]
    }

    entries = []

    for ex in exercises[day]:
        st.subheader(ex)

        sets = st.number_input(f"Sets {ex}", 1, 6, 3, key=ex)
        reps = st.number_input(f"Avg reps {ex}", 0, 30, 10, key=ex+"r")
        rpe = st.slider(f"RPE {ex}", 1, 10, 8, key=ex+"rpe")
        weight = st.number_input(f"Weight {ex}", 0.0, 300.0, 20.0, key=ex+"w")

        suggestion, action = suggest(weight, reps, rpe)

        st.info(f"{action}: {suggestion}")

        entries.append({
            "user_id": user_id,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "exercise": ex,
            "weight": weight,
            "reps": reps,
            "sets": sets,
            "rpe": rpe,
            "volume": sets * reps * weight,
            "suggestion": suggestion,
            "action": action
        })

    if st.button("Save"):
        supabase.table("workouts").insert(entries).execute()
        st.success("Saved!")

    # -------- LOAD USER DATA -------- #

    res = supabase.table("workouts").select("*").eq("user_id", user_id).execute()

    if res.data:
        df = pd.DataFrame(res.data)

        st.subheader("Progress")
        st.line_chart(df.groupby("date")["volume"].sum())
        st.dataframe(df.tail(20))


# ---------------- ROUTER ---------------- #

if "user" not in st.session_state:
    login_ui()
else:
    if st.button("Logout"):
        st.session_state.pop("user")
        st.rerun()

    app()
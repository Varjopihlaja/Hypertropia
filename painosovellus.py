# =========================================================
# CONSISTENCY CHECK (3 SESSION RULE - FIXED)
# =========================================================

def is_consistent(df_ex):
    if len(df_ex) < 3:
        return False

    last3 = df_ex.sort_values("date").tail(3)

    return all(row["avg_reps"] >= 12 for _, row in last3.iterrows())


# =========================================================
# PROGRESSION (FIXED LOGIC)
# =========================================================

def progression(ex, reps, rpe, weight):

    avg = sum(reps) / len(reps)
    step = get_step(ex, weight)

    df_ex = df[df["exercise"] == ex]

    # fatigue rule
    if rpe >= 9:
        return snap(weight * 0.97, step), "fatigue drop"

    # ONLY progress if consistent across sessions
    if is_consistent(df_ex) and avg >= 12 and rpe <= 8:
        return snap(weight + step, step), "progress (consistent 3-sessions)"

    if avg < 8:
        return weight, "build reps"

    return weight, "maintain"


# =========================================================
# SAFE SUPABASE SAVE (FIXED RLS + CRASH PROTECTION)
# =========================================================

def save_data(session):
    for r in session:
        try:
            res = supabase.table("workouts").insert(r).execute()
            if res.data is None:
                st.warning("Insert may have failed (check Supabase RLS policies)")
        except Exception as e:
            st.error(f"Save failed: {e}")


# =========================================================
# TRAIN UI FIXED (TYPE + AUTO WEIGHT FIX)
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

            df_ex = df[df["exercise"] == ex]

            base_weight = float(last["weight"]) if last else 20.0

            # 👉 AUTO PROGRESSION PREVIEW (what today should suggest)
            if len(df_ex) >= 3 and is_consistent(df_ex):
                recommended_weight = snap(base_weight + get_step(ex, base_weight), get_step(ex, base_weight))
            else:
                recommended_weight = base_weight

            sets = st.number_input(
                "Sets",
                0, 6,
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

            # ✅ FIX STREAMLIT TYPE ERROR
            weight = st.number_input(
                "Weight",
                min_value=0.0,
                max_value=300.0,
                value=float(recommended_weight),
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
                "sets": int(sets),
                "reps_list": reps,
                "avg_reps": float(sum(reps) / len(reps)),
                "rpe": float(rpe),
                "weight": float(weight),
                "volume": float(sum(reps) * weight)
            })


# =========================================================
# PR TRACKING (EPLEY FIXED)
# =========================================================

elif page == "PR Tracking":

    if not df.empty:
        df["est_1rm"] = df.apply(
            lambda x: x["weight"] * (1 + x["avg_reps"] / 30),  # Epley formula
            axis=1
        )

        for ex in df["exercise"].unique():
            pr = df[df["exercise"] == ex]["est_1rm"].max()
            st.write(ex, "→", round(pr, 1))
    else:
        st.write("No data")

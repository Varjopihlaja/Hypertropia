# NEXT SESSION RECOMMENDATION (FIXED LOGIC)
# =========================

def get_step(ex):
    return 1.25 if "machine row" in ex.lower() else 2.5
if page == "Progression" and d is not None and not d.empty:

step = get_step(ex)
    def get_step(ex):
        return 1.25 if "machine row" in ex.lower() else 2.5

last_weight = float(last["weight"])
last_reps = float(last["avg_reps"])
last_rpe = float(last["rpe"])
    last = d.iloc[-1]

# target zone (hypertrophy logic)
target_low = 8
target_high = 12
    step = get_step(ex)

next_weight = last_weight
    last_weight = float(last["weight"])
    last_reps = float(last["avg_reps"])
    last_rpe = float(last["rpe"])

# RULE 1: too easy → increase weight
if last_reps > target_high and last_rpe <= 8:
    next_weight += step
    # target zone (hypertrophy logic)
    target_low = 8
    target_high = 12

# RULE 2: too hard → decrease weight
elif last_reps < target_low or last_rpe >= 9:
    next_weight -= step
    next_weight = last_weight

# RULE 3: perfect zone → small progression
else:
    next_weight += step * 0.5
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
    # safety clamp (prevents weird drift)
    next_weight = max(1.0, round(next_weight, 1))

st.markdown("### Suggested Next Session")
st.write(f"Recommended weight: **{next_weight:.1f} kg**")
st.write("Target: 8–12 reps @ RPE 7–9")
    st.markdown("### Suggested Next Session")
    st.write(f"Recommended weight: **{next_weight:.1f} kg**")
    st.write("Target: 8–12 reps @ RPE 7–9")

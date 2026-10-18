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

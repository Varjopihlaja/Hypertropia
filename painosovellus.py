# =========================================================

elif page == "Fatigue Planner":
    st.title("Fatigue Curves with Forecast")
    st.title("Fatigue Monitor (Improved)")

    weekly = weekly_fatigue(df)
    if weekly.empty:
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

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

    left, right = st.columns(2)
    # =========================
    # DAILY LOAD
    # =========================
    daily = d.groupby("date")["volume"].sum().reset_index()
    daily = daily.sort_values("date")

    upper = weekly[weekly["muscle"] != "legs"].groupby("week")["volume"].sum().reset_index()
    lower = weekly[weekly["muscle"] == "legs"].groupby("week")["volume"].sum().reset_index()
    # =========================
    # FATIGUE MODEL
    # =========================
    def rolling_mean(x, w):
        return x.rolling(w, min_periods=1).mean()

    hist_u, fut_u = forecast(upper, "week", "volume")
    hist_l, fut_l = forecast(lower, "week", "volume")
    daily["acute"] = rolling_mean(daily["volume"], 7)
    daily["chronic"] = rolling_mean(daily["volume"], 28)

    with left:
        st.subheader("Upper Body")
        st.line_chart(hist_u.set_index("week")["volume"])
        if fut_u is not None:
            st.line_chart(fut_u.set_index("week")["volume"])
    daily["fatigue_index"] = daily["acute"] / daily["chronic"].replace(0, np.nan)
    daily["fatigue_index"] = daily["fatigue_index"].fillna(1.0)

    with right:
        st.subheader("Lower Body")
        st.line_chart(hist_l.set_index("week")["volume"])
        if fut_l is not None:
            st.line_chart(fut_l.set_index("week")["volume"])
    # =========================
    # GUIDELINES
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

    # =========================
    # METRICS
    # =========================
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
    # CHART (SINGLE FIGURE)
    # =========================
    import altair as alt

    base = alt.Chart(daily).encode(
        x=alt.X("date:T", axis=alt.Axis(format="%d.%m.%Y"))
    )

    load_line = base.mark_line(color="blue", strokeWidth=2).encode(
        y="volume:Q",
        tooltip=["date", "volume"]
    )

    fatigue_line = base.mark_line(color="red", strokeWidth=2).encode(
        y="fatigue_index:Q",
        tooltip=["date", "fatigue_index"]
    )

    guideline = pd.DataFrame({
        "y": [0.8, 1.3, 1.6],
        "label": ["low", "optimal", "high"]
    })

    rules = alt.Chart(guideline).mark_rule(strokeDash=[4,4]).encode(
        y="y:Q"
    )

    st.altair_chart(load_line + fatigue_line + rules, use_container_width=True)

    st.markdown("""
    ### Fatigue Guidelines
    - **< 0.8** → Undertraining  
    - **0.8 – 1.3** → Optimal range  
    - **1.3 – 1.6** → High fatigue  
    - **> 1.6** → Overreaching / deload needed  
    """)


#################################################
# PROGRESSION
#################################################

elif page == "Progression":
st.title("Strength Progression Intelligence")

elif latest["fatigue_index"] < 0.8:
st.info("Low training stimulus")

# =========================
# VISUALIZATION (PER MUSCLE)
# =========================

import altair as alt

muscles = sorted(daily["muscle"].dropna().unique())
selected_muscle = st.selectbox("Select muscle group", muscles)

plot_df = daily[daily["muscle"] == selected_muscle].copy()

if plot_df.empty:
    st.info("No data for selected muscle.")
    st.stop()

base = alt.Chart(plot_df).encode(
    x=alt.X("date:T", axis=alt.Axis(format="%d.%m"))
)

# Fatigue index line
fatigue_line = base.mark_line(point=True).encode(
    y=alt.Y("fatigue_index:Q", title="Fatigue Index"),
    tooltip=["date", "fatigue_index", "acute", "chronic"]
)

# Acute & Chronic lines (scaled but visible)
acute_line = base.mark_line(color="red", strokeDash=[4, 4]).encode(
    y="acute:Q",
    tooltip=["date", "acute"]
)

chronic_line = base.mark_line(color="black", strokeDash=[6, 6]).encode(
    y="chronic:Q",
    tooltip=["date", "chronic"]
)

# Reference zones (correct fatigue index scale)
zones = pd.DataFrame({
    "y": [0.8, 1.3, 1.6]
})

zone_lines = alt.Chart(zones).mark_rule(strokeDash=[5, 5]).encode(
    y="y:Q"
)

st.altair_chart(
    (fatigue_line + zone_lines).resolve_scale(y="independent"),
    use_container_width=True
)

st.caption("""
Red dashed = acute load (recent stress)  
Black dashed = chronic load (baseline capacity)  
Fatigue line = acute ÷ chronic  
""")
    # =========================
    # VISUALIZATION (PER MUSCLE)
    # =========================
    
    import altair as alt
    
    muscles = sorted(daily["muscle"].dropna().unique())
    selected_muscle = st.selectbox("Select muscle group", muscles)
    
    plot_df = daily[daily["muscle"] == selected_muscle].copy()
    
    if plot_df.empty:
        st.info("No data for selected muscle.")
        st.stop()
    
    base = alt.Chart(plot_df).encode(
        x=alt.X("date:T", axis=alt.Axis(format="%d.%m"))
    )
    
    # Fatigue index line
    fatigue_line = base.mark_line(point=True).encode(
        y=alt.Y("fatigue_index:Q", title="Fatigue Index"),
        tooltip=["date", "fatigue_index", "acute", "chronic"]
    )
    
    # Acute & Chronic lines (scaled but visible)
    acute_line = base.mark_line(color="red", strokeDash=[4, 4]).encode(
        y="acute:Q",
        tooltip=["date", "acute"]
    )
    
    chronic_line = base.mark_line(color="black", strokeDash=[6, 6]).encode(
        y="chronic:Q",
        tooltip=["date", "chronic"]
    )
    
    # Reference zones (correct fatigue index scale)
    zones = pd.DataFrame({
        "y": [0.8, 1.3, 1.6]
    })
    
    zone_lines = alt.Chart(zones).mark_rule(strokeDash=[5, 5]).encode(
        y="y:Q"
    )
    
    st.altair_chart(
        (fatigue_line + zone_lines).resolve_scale(y="independent"),
        use_container_width=True
    )
    
    st.caption("""
    Red dashed = acute load (recent stress)  
    Black dashed = chronic load (baseline capacity)  
    Fatigue line = acute ÷ chronic  
    """)

st.markdown("""
   ### Interpretation

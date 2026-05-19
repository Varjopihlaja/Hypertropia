# =========================================================

elif page == "Fatigue Planner":
    st.title("Fatigue Monitor (Improved)")
    st.title("Fatigue Monitor")

df["date"] = pd.to_datetime(df["date"], errors="coerce")

    st.markdown("""
    **Acute load** = last 7 days training stress (what you did recently)  
    **Chronic load** = last 28 days training baseline (your normal capacity)  
    → Fatigue = how much recent work deviates from your baseline
    """)

view = st.selectbox("Time window", ["1 Week", "1 Month", "All Time"])

# =========================
@@ -593,23 +599,20 @@ def status(row):
# =========================
# DAILY LOAD
# =========================
    daily = d.groupby("date")["volume"].sum().reset_index()
    daily = d.groupby(["date", "muscle"])["volume"].sum().reset_index()
daily = daily.sort_values("date")

    # =========================
    # FATIGUE MODEL
    # =========================
def rolling_mean(x, w):
return x.rolling(w, min_periods=1).mean()

    daily["acute"] = rolling_mean(daily["volume"], 7)
    daily["chronic"] = rolling_mean(daily["volume"], 28)
    daily["acute"] = daily.groupby("muscle")["volume"].transform(lambda x: rolling_mean(x, 7))
    daily["chronic"] = daily.groupby("muscle")["volume"].transform(lambda x: rolling_mean(x, 28))

daily["fatigue_index"] = daily["acute"] / daily["chronic"].replace(0, np.nan)
daily["fatigue_index"] = daily["fatigue_index"].fillna(1.0)

# =========================
    # GUIDELINES
    # ZONES
# =========================
def zone(x):
if x < 0.8:
@@ -622,13 +625,9 @@ def zone(x):

daily["zone"] = daily["fatigue_index"].apply(zone)

    # =========================
    # METRICS
    # =========================
latest = daily.iloc[-1]

col1, col2, col3 = st.columns(3)

col1.metric("Acute Load", round(latest["acute"], 1))
col2.metric("Chronic Load", round(latest["chronic"], 1))
col3.metric("Fatigue Index", round(latest["fatigue_index"], 2))
@@ -641,44 +640,41 @@ def zone(x):
st.info("Low training stimulus")

# =========================
    # CHART (SINGLE FIGURE)
    # VISUALIZATION (BETTER)
# =========================
import altair as alt

base = alt.Chart(daily).encode(
        x=alt.X("date:T", axis=alt.Axis(format="%d.%m.%Y"))
        x=alt.X("date:T", axis=alt.Axis(format="%d.%m"))
)

    load_line = base.mark_line(color="blue", strokeWidth=2).encode(
        y="volume:Q",
        tooltip=["date", "volume"]
    # Fatigue line per muscle
    fatigue_line = base.mark_line(point=True).encode(
        y=alt.Y("fatigue_index:Q", title="Fatigue Index"),
        color=alt.Color("muscle:N", title="Muscle"),
        tooltip=["date", "muscle", "fatigue_index", "acute", "chronic"]
)

    fatigue_line = base.mark_line(color="red", strokeWidth=2).encode(
        y="fatigue_index:Q",
        tooltip=["date", "fatigue_index"]
    )

    guideline = pd.DataFrame({
    # Reference zone lines
    zones = pd.DataFrame({
"y": [0.8, 1.3, 1.6],
        "label": ["low", "optimal", "high"]
        "label": ["Under", "Optimal", "High"]
})

    rules = alt.Chart(guideline).mark_rule(strokeDash=[4,4]).encode(
    zone_lines = alt.Chart(zones).mark_rule(strokeDash=[6, 6]).encode(
y="y:Q"
)

    st.altair_chart(load_line + fatigue_line + rules, use_container_width=True)
    st.altair_chart(fatigue_line + zone_lines, use_container_width=True)

st.markdown("""
    ### Fatigue Guidelines
    - **< 0.8** → Undertraining  
    - **0.8 – 1.3** → Optimal range  
    - **1.3 – 1.6** → High fatigue  
    - **> 1.6** → Overreaching / deload needed  
    ### Interpretation
    - **Acute load** → recent stress (fatigue today)  
    - **Chronic load** → long-term capacity (fitness baseline)  
    - **Fatigue index > 1.3** → accumulating fatigue  
    - **< 0.8** → undertraining / underload  
   """)


#################################################
# PROGRESSION
#################################################

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Puffy A/B Test Dashboard", layout="wide")

st.title("🧪 Puffy Lux PDP Redesign — A/B Experiment Analysis")
st.markdown(
    "**Arm A (Control)** vs **Arm B (Variant)** Behavioral & Financial"
    " Performance"
)

# Load data
df_funnel = pd.read_csv("1_linear_funnel.csv")
df_rev = pd.read_csv("2_revenue_metrics.csv")
df_cond = pd.read_csv("3_conditional_behavior.csv")

# Top KPI Metrics
col1, col2, col3, col4 = st.columns(4)
rpu_a = df_rev[df_rev["arm"] == "a"]["revenue_per_user_rpu"].values[0]
rpu_b = df_rev[df_rev["arm"] == "b"]["revenue_per_user_rpu"].values[0]
conv_a = df_funnel[df_funnel["arm"] == "a"]["conversion_pct"].values[0]
conv_b = df_funnel[df_funnel["arm"] == "b"]["conversion_pct"].values[0]

col1.metric("Arm A Conv Rate", f"{conv_a}%")
col2.metric(
    "Arm B Conv Rate", f"{conv_b}%", delta=f"{conv_b - conv_a:.2f}%", delta_color="inverse"
)
col3.metric("Arm A Rev/User (RPU)", f"${rpu_a}")
col4.metric(
    "Arm B Rev/User (RPU)", f"${rpu_b}", delta=f"${rpu_b - rpu_a:.2f}", delta_color="inverse"
)

st.divider()

# Charts in 2 Columns
left_col, right_col = st.columns(2)

with left_col:
    st.subheader("1. Linear Conversion Rates (%)")
    fig1 = px.bar(
        df_funnel,
        x="arm",
        y=["size_changed_pct", "atc_pct", "conversion_pct"],
        barmode="group",
        labels={
            "value": "Percentage (%)",
            "variable": "Funnel Step",
            "arm": "Arm",
        },
        color_discrete_sequence=["#1f77b4", "#ff7f0e", "#2ca02c"],
    )
    st.plotly_chart(fig1, use_container_width=True)

with right_col:
    st.subheader("2. Conditional Behavioral Conversion Rate")
    fig2 = px.bar(
        df_cond,
        x="user_segment",
        y="purchase_rate_pct",
        color="arm",
        barmode="group",
        labels={
            "purchase_rate_pct": "Purchase Rate (%)",
            "user_segment": "User Segment",
        },
    )
    st.plotly_chart(fig2, use_container_width=True)
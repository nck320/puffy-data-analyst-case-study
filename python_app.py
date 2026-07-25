import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# -----------------------------------------------------------------------------
# 1. Page Configuration & Executive CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Puffy Lux PDP Redesign — A/B Experiment Analysis (Pandas)",
    page_icon="🐍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main {
        padding-top: 1rem;
    }
    h1 {
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    .stMetric label {
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        color: #A1A1AA !important;
    }
    .stMetric [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
    }
    div[data-testid="stContainer"] {
        border-radius: 10px;
    }
    </style>
""",
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# 2. Dynamic Pipeline (Pure Pandas Direct Processing)
# -----------------------------------------------------------------------------
@st.cache_data
def run_python_pipeline():
  events = pd.read_csv("ab_hero_v4_events.csv")
  orders = pd.read_csv("ab_hero_v4_order_line_items.csv")

  def parse_json(val, k):
    try:
      return json.loads(val).get(k)
    except:
      return None

  # Parse experiment assignment
  ab_init = events[events["event_name"] == "ab_experiment_init"].copy()
  ab_init["arm"] = ab_init["event_data"].apply(
      lambda x: parse_json(x, "experiment_var")
  )
  ab_init = ab_init.dropna(subset=["arm"]).sort_values("ingestion_timestamp")
  user_arms = ab_init.groupby("client_id")["arm"].first().reset_index()

  df = events.merge(user_arms, on="client_id", how="inner")
  valid = df[df["session_traffic_quality"] == "valid"].copy()
  totals = valid.groupby("arm")["client_id"].nunique().to_dict()

  # 1. Linear Funnel
  funnel_data = []
  for arm in ["a", "b"]:
    sub = valid[valid["arm"] == arm]
    b_u = totals[arm]
    sc = sub[sub["event_name"] == "size_changed"]["client_id"].nunique()
    atc = sub[sub["event_name"] == "product_added_to_cart"]["client_id"].nunique()
    co = sub[sub["event_name"] == "checkout_completed"]["client_id"].nunique()
    funnel_data.append({
        "arm": arm,
        "base_users": b_u,
        "size_changed_pct": round((sc / b_u) * 100, 2),
        "atc_pct": round((atc / b_u) * 100, 2),
        "conversion_pct": round((co / b_u) * 100, 2),
    })
  df_funnel = pd.DataFrame(funnel_data)

  # 2. Revenue & AOV
  cc = valid[valid["event_name"] == "checkout_completed"].copy()
  cc["order_id"] = pd.to_numeric(
      cc["event_data"].apply(lambda x: parse_json(x, "order_id")),
      errors="coerce",
  )
  cc_orders = cc[["client_id", "arm", "order_id"]].drop_duplicates()
  merged_orders = orders.merge(cc_orders, on="order_id", how="inner")
  order_tot = (
      merged_orders.groupby(["order_id", "arm"])["value"].sum().reset_index()
  )

  rev_data = []
  for arm in ["a", "b"]:
    sub = order_tot[order_tot["arm"] == arm]
    b_u = totals[arm]
    tot_rev = sub["value"].sum()
    rev_data.append({
        "arm": arm,
        "avg_order_value_aov": round(sub["value"].mean(), 2),
        "revenue_per_user_rpu": round(tot_rev / b_u, 2),
    })
  df_revenue = pd.DataFrame(rev_data)

  # 3. Conditional Behavior
  flags = (
      valid.groupby(["client_id", "arm"])
      .agg(
          has_sc=("event_name", lambda x: int((x == "size_changed").any())),
          has_co=(
              "event_name",
              lambda x: int((x == "checkout_completed").any()),
          ),
      )
      .reset_index()
  )

  cond_data = []
  for arm in ["a", "b"]:
    sub = flags[flags["arm"] == arm]
    for val, name in [(1, "Size Selector"), (0, "Default Bypasser")]:
      seg = sub[sub["has_sc"] == val]
      cond_data.append({
          "arm": arm,
          "user_segment": name,
          "purchase_rate_pct": round(seg["has_co"].mean() * 100, 2),
      })
  df_cond = pd.DataFrame(cond_data)

  # 4. Scroll Reachability Curve
  scrolls = valid[valid["event_name"] == "scroll"].copy()
  scrolls["depth"] = pd.to_numeric(
      scrolls["event_data"].apply(lambda x: parse_json(x, "scroll_depth_pct")),
      errors="coerce",
  )
  user_scroll = (
      scrolls.groupby(["client_id", "arm"])["depth"].max().reset_index()
  )

  scroll_reach = []
  for arm in ["a", "b"]:
    b_u = totals[arm]
    sub = user_scroll[user_scroll["arm"] == arm]
    for d in [10, 25, 50, 75, 100]:
      reach = (sub["depth"] >= d).sum()
      scroll_reach.append({
          "arm": arm,
          "Depth": f"{d}%",
          "Reach_Pct": round((reach / b_u) * 100, 2),
      })
  df_scroll = pd.DataFrame(scroll_reach)

  # 5. Device Friction
  dev_data = []
  for (arm, device), group in valid.groupby(["arm", "device"]):
    tot = group["client_id"].nunique()
    sc_cnt = group[group["event_name"] == "size_changed"]["client_id"].nunique()
    dev_data.append({
        "arm": arm,
        "device": device,
        "size_selector_pct": round((sc_cnt / tot) * 100, 2),
    })
  df_device = pd.DataFrame(dev_data)

  # 6. Attribution
  cr_a = (
      df_funnel[df_funnel["arm"] == "a"]["conversion_pct"].values[0] / 100.0
  )
  cr_b = (
      df_funnel[df_funnel["arm"] == "b"]["conversion_pct"].values[0] / 100.0
  )
  aov_a = df_revenue[df_revenue["arm"] == "a"]["avg_order_value_aov"].values[0]
  aov_b = df_revenue[df_revenue["arm"] == "b"]["avg_order_value_aov"].values[0]
  rpu_a = df_revenue[df_revenue["arm"] == "a"]["revenue_per_user_rpu"].values[0]
  rpu_b = df_revenue[df_revenue["arm"] == "b"]["revenue_per_user_rpu"].values[0]

  df_attr = pd.DataFrame([{
      "cr_impact": round((cr_b - cr_a) * aov_a, 2),
      "aov_impact": round(cr_b * (aov_b - aov_a), 2),
      "total_rpu_delta": round(rpu_b - rpu_a, 2),
  }])

  return df_funnel, df_revenue, df_cond, df_scroll, df_device, df_attr


try:
  df_funnel, df_revenue, df_cond, df_scroll, df_device, df_attr = (
      run_python_pipeline()
  )
except Exception as e:
  st.error(
      "Error processing raw CSV files with Pandas. Ensure"
      " `ab_hero_v4_events.csv` and `ab_hero_v4_order_line_items.csv` exist."
      f" Details: {e}"
  )
  st.stop()

arm_map = {"a": "Arm A (Control)", "b": "Arm B (Variant)"}

# -----------------------------------------------------------------------------
# 3. Header Section
# -----------------------------------------------------------------------------
st.title("🧪 Puffy Lux PDP Redesign — A/B Experiment Analysis (Pandas)")
st.caption(
    "Arm A (Control) vs. Arm B (Variant) Behavioral & Financial Performance"
    " Audit"
)
st.markdown("---")

# -----------------------------------------------------------------------------
# 4. KPI Summary Panel
# -----------------------------------------------------------------------------
cr_a = df_funnel[df_funnel["arm"] == "a"]["conversion_pct"].values[0]
cr_b = df_funnel[df_funnel["arm"] == "b"]["conversion_pct"].values[0]
rpu_a = df_revenue[df_revenue["arm"] == "a"]["revenue_per_user_rpu"].values[0]
rpu_b = df_revenue[df_revenue["arm"] == "b"]["revenue_per_user_rpu"].values[0]

with st.container(border=True):
  col1, col2, col3, col4 = st.columns(4)
  with col1:
    st.metric(label="Arm A Conv Rate", value=f"{cr_a:.2f}%")
  with col2:
    st.metric(
        label="Arm B Conv Rate",
        value=f"{cr_b:.2f}%",
        delta=f"{cr_b - cr_a:.2f}%",
        delta_color="normal",
    )
  with col3:
    st.metric(label="Arm A Rev/User (RPU)", value=f"${rpu_a:.2f}")
  with col4:
    st.metric(
        label="Arm B Rev/User (RPU)",
        value=f"${rpu_b:.2f}",
        delta=f"-${abs(rpu_b - rpu_a):.2f}",
        delta_color="normal",
    )

st.write("")

# -----------------------------------------------------------------------------
# 5. Visualizations Section
# -----------------------------------------------------------------------------
col_left, col_right = st.columns(2)

# --- LEFT PANEL: Linear Engagement Funnel ---
with col_left:
  with st.container(border=True):
    st.subheader("1. Linear Engagement Metrics (%)")
    st.caption(
        "Comparison of Size Interaction, Add-to-Cart, and Conversion rates."
    )

    df_funnel_plot = df_funnel.melt(
        id_vars=["arm"],
        value_vars=["size_changed_pct", "atc_pct", "conversion_pct"],
        var_name="Metric",
        value_name="Percentage",
    )
    df_funnel_plot["Arm_Label"] = df_funnel_plot["arm"].map(arm_map)
    df_funnel_plot["Metric"] = df_funnel_plot["Metric"].map({
        "size_changed_pct": "Size Changed",
        "atc_pct": "Add To Cart",
        "conversion_pct": "Conversion",
    })

    fig_funnel = px.bar(
        df_funnel_plot,
        x="Arm_Label",
        y="Percentage",
        color="Metric",
        barmode="group",
        category_orders={"Arm_Label": ["Arm A (Control)", "Arm B (Variant)"]},
        color_discrete_sequence=["#6366F1", "#06B6D4", "#10B981"],
        labels={
            "Percentage": "Percentage (%)",
            "Arm_Label": "Experiment Arm",
            "Metric": "Metric",
        },
    )
    fig_funnel.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=380,
        margin=dict(l=20, r=20, t=20, b=20),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
    )
    st.plotly_chart(fig_funnel, use_container_width=True)

# --- RIGHT PANEL: Conditional Behavioral Segmentation ---
with col_right:
  with st.container(border=True):
    st.subheader("2. Conditional Purchase Rate by Segment")
    st.caption("Conversion rate split by Size Selectors vs. Default Bypassers.")

    df_cond_plot = df_cond.copy()
    df_cond_plot["Arm_Label"] = df_cond_plot["arm"].map(arm_map)

    fig_cond = px.bar(
        df_cond_plot,
        x="user_segment",
        y="purchase_rate_pct",
        color="Arm_Label",
        barmode="group",
        category_orders={"Arm_Label": ["Arm A (Control)", "Arm B (Variant)"]},
        color_discrete_sequence=["#818CF8", "#38BDF8"],
        labels={
            "purchase_rate_pct": "Purchase Rate (%)",
            "user_segment": "User Segment",
            "Arm_Label": "Arm",
        },
    )
    fig_cond.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=380,
        margin=dict(l=20, r=20, t=20, b=20),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
    )
    st.plotly_chart(fig_cond, use_container_width=True)

# -----------------------------------------------------------------------------
# 6. Scroll Telemetry & Financial Attribution
# -----------------------------------------------------------------------------
col_scroll, col_attr = st.columns(2)

with col_scroll:
  with st.container(border=True):
    st.subheader("3. Scroll Depth Telemetry & Reachability")
    st.caption("Percentage of users reaching key PDP interaction thresholds.")

    df_scroll_plot = df_scroll.copy()
    df_scroll_plot["Arm_Label"] = df_scroll_plot["arm"].map(arm_map)

    fig_scroll = px.line(
        df_scroll_plot,
        x="Depth",
        y="Reach_Pct",
        color="Arm_Label",
        markers=True,
        category_orders={"Arm_Label": ["Arm A (Control)", "Arm B (Variant)"]},
        color_discrete_sequence=["#6366F1", "#F43F5E"],
        labels={
            "Reach_Pct": "User Reach (%)",
            "Depth": "Scroll Depth",
            "Arm_Label": "Arm",
        },
    )
    fig_scroll.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=320,
        margin=dict(l=20, r=20, t=20, b=20),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
    )
    st.plotly_chart(fig_scroll, use_container_width=True)

with col_attr:
  with st.container(border=True):
    st.subheader("4. RPU Loss Attribution Breakdown")
    st.caption("Mathematical breakdown of RPU drop (Conversion vs AOV).")

    cr_imp = df_attr["cr_impact"].values[0]
    aov_imp = df_attr["aov_impact"].values[0]
    tot_delta = df_attr["total_rpu_delta"].values[0]

    fig_water = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=["relative", "relative", "total"],
            x=["Conversion Drop", "AOV Drift", "Net RPU Delta"],
            y=[cr_imp, aov_imp, tot_delta],
            text=[f"${cr_imp}", f"${aov_imp}", f"${tot_delta}"],
            textposition="outside",
            connector={"line": {"color": "rgb(63, 63, 63)"}},
            decreasing={"marker": {"color": "#F43F5E"}},
            totals={"marker": {"color": "#3B82F6"}},
        )
    )
    fig_water.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=320,
        margin=dict(l=20, r=20, t=20, b=20),
        yaxis_title="RPU Impact ($)",
    )
    st.plotly_chart(fig_water, use_container_width=True)

# -----------------------------------------------------------------------------
# 7. Sidebar Information & Links
# -----------------------------------------------------------------------------
with st.sidebar:
  st.title("📌 Case Study Overview")
  st.markdown("""
    **Project:** Puffy Lux PDP A/B Test  
    **Author:** Nihal Rajeev Sainudeen  
    **Role:** Data Analyst / Engineer  
    """)
  st.markdown("---")
  st.markdown("### Key Takeaway")
  st.info("""
    **Arm B suffered from UX friction.**
    While Arm B Size Selectors convert well, lower scroll reach led more users to bypass selector interaction entirely, driving down total revenue.
    """)
  st.markdown("---")
  st.markdown(
      "[📂 GitHub"
      " Repository](https://github.com/nck320/puffy-data-analyst-case-study)"
  )
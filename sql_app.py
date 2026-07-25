import duckdb
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# -----------------------------------------------------------------------------
# 1. Page Configuration & Executive CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Puffy Lux PDP Redesign — A/B Experiment Intelligence (SQL)",
    page_icon="⚡",
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
# 2. Dynamic Pipeline (DuckDB Direct Processing)
# -----------------------------------------------------------------------------
@st.cache_data
def run_sql_pipeline():
  con = duckdb.connect()

  # 1. Linear Funnel
  df_funnel = con.execute("""
    WITH user_arm AS (
        SELECT client_id, json_extract_string(event_data, '$.experiment_var') AS arm,
               ROW_NUMBER() OVER (PARTITION BY client_id ORDER BY ingestion_timestamp ASC) AS rn
        FROM read_csv_auto('ab_hero_v4_events.csv')
        WHERE event_name = 'ab_experiment_init'
    ),
    valid_events AS (
        SELECT e.*, u.arm FROM read_csv_auto('ab_hero_v4_events.csv') e
        JOIN user_arm u ON e.client_id = u.client_id 
        WHERE u.rn = 1 AND u.arm IS NOT NULL AND e.session_traffic_quality = 'valid'
    ),
    totals AS (
        SELECT arm, COUNT(DISTINCT client_id) AS base_users FROM valid_events GROUP BY arm
    )
    SELECT 
        v.arm,
        t.base_users,
        COUNT(DISTINCT CASE WHEN event_name = 'page_viewed' THEN client_id END) AS page_viewed,
        COUNT(DISTINCT CASE WHEN event_name = 'size_changed' THEN client_id END) AS size_changed,
        ROUND(COUNT(DISTINCT CASE WHEN event_name = 'size_changed' THEN client_id END) * 100.0 / t.base_users, 2) AS size_changed_pct,
        COUNT(DISTINCT CASE WHEN event_name = 'product_added_to_cart' THEN client_id END) AS atc,
        ROUND(COUNT(DISTINCT CASE WHEN event_name = 'product_added_to_cart' THEN client_id END) * 100.0 / t.base_users, 2) AS atc_pct,
        COUNT(DISTINCT CASE WHEN event_name = 'checkout_completed' THEN client_id END) AS completed,
        ROUND(COUNT(DISTINCT CASE WHEN event_name = 'checkout_completed' THEN client_id END) * 100.0 / t.base_users, 2) AS conversion_pct
    FROM valid_events v
    JOIN totals t ON v.arm = t.arm
    GROUP BY v.arm, t.base_users
    ORDER BY v.arm;
    """).df()

  # 2. Revenue & AOV
  df_revenue = con.execute("""
    WITH user_arm AS (
        SELECT client_id, json_extract_string(event_data, '$.experiment_var') AS arm,
               ROW_NUMBER() OVER (PARTITION BY client_id ORDER BY ingestion_timestamp ASC) AS rn
        FROM read_csv_auto('ab_hero_v4_events.csv')
        WHERE event_name = 'ab_experiment_init'
    ),
    valid_events AS (
        SELECT e.*, u.arm FROM read_csv_auto('ab_hero_v4_events.csv') e
        JOIN user_arm u ON e.client_id = u.client_id 
        WHERE u.rn = 1 AND u.arm IS NOT NULL AND e.session_traffic_quality = 'valid'
    ),
    totals AS (
        SELECT arm, COUNT(DISTINCT client_id) AS base_users FROM valid_events GROUP BY arm
    ),
    orders_parsed AS (
        SELECT DISTINCT client_id, arm,
               TRY_CAST(json_extract_string(event_data, '$.order_id') AS INT64) AS order_id
        FROM valid_events WHERE event_name = 'checkout_completed'
    ),
    order_vals AS (
        SELECT o.arm, o.order_id, SUM(i.value) AS order_total
        FROM orders_parsed o
        JOIN read_csv_auto('ab_hero_v4_order_line_items.csv') i ON o.order_id = i.order_id
        GROUP BY o.arm, o.order_id
    )
    SELECT 
        v.arm,
        t.base_users,
        COUNT(v.order_id) AS total_orders,
        ROUND(AVG(v.order_total), 2) AS avg_order_value_aov,
        ROUND(SUM(v.order_total), 2) AS total_revenue,
        ROUND(SUM(v.order_total) / t.base_users, 2) AS revenue_per_user_rpu
    FROM order_vals v
    JOIN totals t ON v.arm = t.arm
    GROUP BY v.arm, t.base_users
    ORDER BY v.arm;
    """).df()

  # 3. Conditional Behavior
  df_cond = con.execute("""
    WITH user_arm AS (
        SELECT client_id, json_extract_string(event_data, '$.experiment_var') AS arm,
               ROW_NUMBER() OVER (PARTITION BY client_id ORDER BY ingestion_timestamp ASC) AS rn
        FROM read_csv_auto('ab_hero_v4_events.csv')
        WHERE event_name = 'ab_experiment_init'
    ),
    valid_events AS (
        SELECT e.*, u.arm FROM read_csv_auto('ab_hero_v4_events.csv') e
        JOIN user_arm u ON e.client_id = u.client_id 
        WHERE u.rn = 1 AND u.arm IS NOT NULL AND e.session_traffic_quality = 'valid'
    ),
    user_flags AS (
        SELECT client_id, arm,
               MAX(CASE WHEN event_name = 'size_changed' THEN 1 ELSE 0 END) AS has_sc,
               MAX(CASE WHEN event_name = 'product_added_to_cart' THEN 1 ELSE 0 END) AS has_atc,
               MAX(CASE WHEN event_name = 'checkout_completed' THEN 1 ELSE 0 END) AS has_co
        FROM valid_events GROUP BY client_id, arm
    )
    SELECT 
        arm,
        CASE WHEN has_sc = 1 THEN 'Size Selector' ELSE 'Default Bypasser' END AS user_segment,
        COUNT(client_id) AS segment_user_count,
        ROUND(AVG(has_atc) * 100.0, 2) AS atc_rate_pct,
        ROUND(AVG(has_co) * 100.0, 2) AS purchase_rate_pct
    FROM user_flags
    GROUP BY arm, CASE WHEN has_sc = 1 THEN 'Size Selector' ELSE 'Default Bypasser' END
    ORDER BY arm, user_segment;
    """).df()

  # 4. Scroll Reachability Curve
  df_scroll = con.execute("""
    WITH user_arm AS (
        SELECT client_id, json_extract_string(event_data, '$.experiment_var') AS arm,
               ROW_NUMBER() OVER (PARTITION BY client_id ORDER BY ingestion_timestamp ASC) AS rn
        FROM read_csv_auto('ab_hero_v4_events.csv')
        WHERE event_name = 'ab_experiment_init'
    ),
    valid_events AS (
        SELECT e.*, u.arm FROM read_csv_auto('ab_hero_v4_events.csv') e
        JOIN user_arm u ON e.client_id = u.client_id 
        WHERE u.rn = 1 AND u.arm IS NOT NULL AND e.session_traffic_quality = 'valid'
    ),
    user_max_scroll AS (
        SELECT client_id, arm,
               MAX(TRY_CAST(json_extract_string(event_data, '$.scroll_depth_pct') AS DOUBLE)) AS max_depth
        FROM valid_events WHERE event_name = 'scroll' GROUP BY client_id, arm
    ),
    arm_totals AS (
        SELECT arm, COUNT(DISTINCT client_id) AS base_users FROM valid_events GROUP BY arm
    )
    SELECT 
        m.arm,
        ROUND(COUNT(DISTINCT CASE WHEN max_depth >= 10 THEN m.client_id END) * 100.0 / t.base_users, 2) AS "10%",
        ROUND(COUNT(DISTINCT CASE WHEN max_depth >= 25 THEN m.client_id END) * 100.0 / t.base_users, 2) AS "25%",
        ROUND(COUNT(DISTINCT CASE WHEN max_depth >= 50 THEN m.client_id END) * 100.0 / t.base_users, 2) AS "50%",
        ROUND(COUNT(DISTINCT CASE WHEN max_depth >= 75 THEN m.client_id END) * 100.0 / t.base_users, 2) AS "75%",
        ROUND(COUNT(DISTINCT CASE WHEN max_depth >= 100 THEN m.client_id END) * 100.0 / t.base_users, 2) AS "100%"
    FROM user_max_scroll m JOIN arm_totals t ON m.arm = t.arm
    GROUP BY m.arm, t.base_users ORDER BY m.arm;
    """).df()

  df_scroll_melted = df_scroll.melt(
      id_vars=["arm"], var_name="Depth", value_name="Reach_Pct"
  )

  # 5. Device Friction
  df_device = con.execute("""
    WITH user_arm AS (
        SELECT client_id, json_extract_string(event_data, '$.experiment_var') AS arm,
               ROW_NUMBER() OVER (PARTITION BY client_id ORDER BY ingestion_timestamp ASC) AS rn
        FROM read_csv_auto('ab_hero_v4_events.csv')
        WHERE event_name = 'ab_experiment_init'
    ),
    valid_events AS (
        SELECT e.*, u.arm FROM read_csv_auto('ab_hero_v4_events.csv') e
        JOIN user_arm u ON e.client_id = u.client_id 
        WHERE u.rn = 1 AND u.arm IS NOT NULL AND e.session_traffic_quality = 'valid'
    )
    SELECT 
        arm, device,
        COUNT(DISTINCT client_id) AS total_users,
        ROUND(COUNT(DISTINCT CASE WHEN event_name = 'size_changed' THEN client_id END) * 100.0 / COUNT(DISTINCT client_id), 2) AS size_selector_pct,
        ROUND(COUNT(DISTINCT CASE WHEN event_name = 'checkout_completed' THEN client_id END) * 100.0 / COUNT(DISTINCT client_id), 2) AS conversion_pct
    FROM valid_events GROUP BY arm, device ORDER BY device, arm;
    """).df()

  # 6. Revenue Loss Attribution
  df_attr = con.execute("""
    WITH user_arm AS (
        SELECT client_id, json_extract_string(event_data, '$.experiment_var') AS arm,
               ROW_NUMBER() OVER (PARTITION BY client_id ORDER BY ingestion_timestamp ASC) AS rn
        FROM read_csv_auto('ab_hero_v4_events.csv')
        WHERE event_name = 'ab_experiment_init'
    ),
    valid_events AS (
        SELECT e.*, u.arm FROM read_csv_auto('ab_hero_v4_events.csv') e
        JOIN user_arm u ON e.client_id = u.client_id 
        WHERE u.rn = 1 AND u.arm IS NOT NULL AND e.session_traffic_quality = 'valid'
    ),
    totals AS (
        SELECT arm, COUNT(DISTINCT client_id) AS base_users FROM valid_events GROUP BY arm
    ),
    orders_parsed AS (
        SELECT DISTINCT client_id, arm,
               TRY_CAST(json_extract_string(event_data, '$.order_id') AS INT64) AS order_id
        FROM valid_events WHERE event_name = 'checkout_completed'
    ),
    order_vals AS (
        SELECT o.arm, o.order_id, SUM(i.value) AS order_total
        FROM orders_parsed o
        JOIN read_csv_auto('ab_hero_v4_order_line_items.csv') i ON o.order_id = i.order_id
        GROUP BY o.arm, o.order_id
    ),
    arm_metrics AS (
        SELECT 
            v.arm, t.base_users,
            COUNT(v.order_id) * 1.0 / t.base_users AS cr,
            AVG(v.order_total) AS aov,
            SUM(v.order_total) / t.base_users AS rpu
        FROM order_vals v JOIN totals t ON v.arm = t.arm GROUP BY v.arm, t.base_users
    )
    SELECT 
        ROUND(a.rpu, 2) AS rpu_a, ROUND(b.rpu, 2) AS rpu_b,
        ROUND(b.rpu - a.rpu, 2) AS total_rpu_delta,
        ROUND((b.cr - a.cr) * a.aov, 2) AS cr_impact,
        ROUND(b.cr * (b.aov - a.aov), 2) AS aov_impact
    FROM arm_metrics a JOIN arm_metrics b ON a.arm = 'a' AND b.arm = 'b';
    """).df()

  return df_funnel, df_revenue, df_cond, df_scroll_melted, df_device, df_attr


try:
  df_funnel, df_revenue, df_cond, df_scroll, df_device, df_attr = (
      run_sql_pipeline()
  )
except Exception as e:
  st.error(
      f"Error running SQL engine on raw CSV files. Ensure `ab_hero_v4_events.csv`"
      f" and `ab_hero_v4_order_line_items.csv` are present. Details: {e}"
  )
  st.stop()

arm_map = {"a": "Arm A (Control)", "b": "Arm B (Variant)"}

# -----------------------------------------------------------------------------
# 3. Header Section
# -----------------------------------------------------------------------------
st.title("🧪 Puffy Lux PDP Redesign — A/B Experiment Analysis (DuckDB)")
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
# 5. Core Visualizations Section
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

# --- RIGHT PANEL: Conditional Purchase Rate ---
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
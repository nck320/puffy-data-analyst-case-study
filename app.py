import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# 1. Page Configuration & Custom CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Puffy Lux PDP Redesign — A/B Experiment Analysis",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for executive polish and badge alignment
st.markdown("""
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
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. Data Loading (Cached for Speed)
# -----------------------------------------------------------------------------
@st.cache_data
def load_data():
    df_funnel = pd.read_csv("1_linear_funnel.csv")
    df_revenue = pd.read_csv("2_revenue_metrics.csv")
    df_conditional = pd.read_csv("3_conditional_behavior.csv")
    df_scroll = pd.read_csv("4_scroll_telemetry.csv")
    return df_funnel, df_revenue, df_conditional, df_scroll

try:
    df_funnel, df_revenue, df_conditional, df_scroll = load_data()
except Exception as e:
    st.error(f"Error loading CSV data files. Please ensure the aggregated CSV files exist in the directory. Details: {e}")
    st.stop()

# Ensure standard labels for Arm A (Control) and Arm B (Variant)
arm_map = {'a': 'Arm A (Control)', 'b': 'Arm B (Variant)'}

# -----------------------------------------------------------------------------
# 3. Header Section
# -----------------------------------------------------------------------------
st.title("🧪 Puffy Lux PDP Redesign — A/B Experiment Analysis")
st.caption("Arm A (Control) vs. Arm B (Variant) Behavioral & Financial Performance Audit")

st.markdown("---")

# -----------------------------------------------------------------------------
# 4. KPI Summary Panel
# -----------------------------------------------------------------------------
with st.container(border=True):
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Arm A Conv Rate",
            value="2.64%"
        )
    with col2:
        st.metric(
            label="Arm B Conv Rate",
            value="1.79%",
            delta="-0.85%",
            delta_color="normal"
        )
    with col3:
        st.metric(
            label="Arm A Rev/User (RPU)",
            value="$52.63"
        )
    with col4:
        st.metric(
            label="Arm B Rev/User (RPU)",
            value="$35.58",
            delta="-$17.05",
            delta_color="normal"
        )

st.write("") # Whitespace

# -----------------------------------------------------------------------------
# 5. Visualizations Section
# -----------------------------------------------------------------------------
col_left, col_right = st.columns(2)

# --- LEFT PANEL: Linear Funnel Performance ---
with col_left:
    with st.container(border=True):
        st.subheader("1. Linear Engagement Metrics (%)")
        st.caption("Comparison of Size Interaction and Add-to-Cart rates across arms.")
        
        df_funnel_plot = df_funnel.copy()
        
        # Ensure 'arm' exists in lowercase
        df_funnel_plot.columns = [c.lower().strip() for c in df_funnel_plot.columns]
        df_funnel_plot['Arm_Label'] = df_funnel_plot['arm'].map(arm_map)
        
        # Determine the correct metric column name dynamically
        metric_col = 'metric_name' if 'metric_name' in df_funnel_plot.columns else df_funnel_plot.columns[1]
        val_col = 'value' if 'value' in df_funnel_plot.columns else df_funnel_plot.columns[2]
        
        fig_funnel = px.bar(
            df_funnel_plot,
            x='Arm_Label',
            y=val_col,
            color=metric_col,
            barmode='group',
            category_orders={'Arm_Label': ['Arm A (Control)', 'Arm B (Variant)']},
            color_discrete_sequence=['#6366F1', '#06B6D4', '#10B981'],
            labels={val_col: 'Percentage (%)', 'Arm_Label': 'Experiment Arm', metric_col: 'Metric'}
        )
        
        fig_funnel.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=380,
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_funnel, use_container_width=True)

# --- RIGHT PANEL: Conditional Behavioral Segmentation ---
with col_right:
    with st.container(border=True):
        st.subheader("2. Conditional Purchase Rate by Segment")
        st.caption("Conversion rate split by Size Selectors vs. Default Bypassers.")
        
        df_cond_plot = df_conditional.copy()
        df_cond_plot.columns = [c.lower().strip() for c in df_cond_plot.columns]
        df_cond_plot['Arm_Label'] = df_cond_plot['arm'].map(arm_map)
        
        # Identify columns dynamically
        seg_col = 'user_segment' if 'user_segment' in df_cond_plot.columns else df_cond_plot.columns[1]
        rate_col = [c for c in df_cond_plot.columns if 'rate' in c or 'pct' in c or 'purchase' in c]
        y_col = rate_col[0] if rate_col else df_cond_plot.columns[2]
        
        fig_cond = px.bar(
            df_cond_plot,
            x=seg_col,
            y=y_col,
            color='Arm_Label',
            barmode='group',
            category_orders={'Arm_Label': ['Arm A (Control)', 'Arm B (Variant)']},
            color_discrete_sequence=['#818CF8', '#38BDF8'],
            labels={y_col: 'Purchase Rate (%)', seg_col: 'User Segment', 'Arm_Label': 'Arm'}
        )
        
        fig_cond.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=380,
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_cond, use_container_width=True)

# -----------------------------------------------------------------------------
# 6. Secondary Deep-Dive Section (Scroll Depth Telemetry)
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("3. Scroll Depth Telemetry & Reachability")
    st.caption("Percentage of users reaching key PDP interaction thresholds.")
    
    if not df_scroll.empty:
        df_scroll_plot = df_scroll.copy()
        df_scroll_plot.columns = [c.lower().strip() for c in df_scroll_plot.columns]
        df_scroll_plot['Arm_Label'] = df_scroll_plot['arm'].map(arm_map)
        
        # Dynamically find x (depth) and y (reach/percentage) columns
        x_col = [c for c in df_scroll_plot.columns if 'depth' in c or 'bucket' in c or 'scroll' in c]
        y_col = [c for c in df_scroll_plot.columns if 'reach' in c or 'pct' in c or 'rate' in c or 'user' in c]
        
        scroll_x = x_col[0] if x_col else df_scroll_plot.columns[1]
        scroll_y = y_col[0] if y_col else df_scroll_plot.columns[2]
        
        fig_scroll = px.line(
            df_scroll_plot,
            x=scroll_x,
            y=scroll_y,
            color='Arm_Label',
            markers=True,
            category_orders={'Arm_Label': ['Arm A (Control)', 'Arm B (Variant)']},
            color_discrete_sequence=['#6366F1', '#F43F5E'],
            labels={scroll_y: 'User Reach (%)', scroll_x: 'Scroll Depth', 'Arm_Label': 'Arm'}
        )
        
        fig_scroll.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=320,
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_scroll, use_container_width=True)
    else:
        st.info("Scroll telemetry data placeholder ready for rendering.")

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
    st.markdown("[📂 GitHub Repository](https://github.com/nck320/puffy-data-analyst-case-study)")
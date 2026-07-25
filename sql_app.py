import io
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -----------------------------------------------------------------------------
# 1. Page Configuration & CSS
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
# 2. CSV Data Ingestion
# -----------------------------------------------------------------------------
@st.cache_data
def load_sql_data():
  df_funnel = pd.read_csv(os.path.join(BASE_DIR, "1_linear_funnel.csv"))
  df_revenue = pd.read_csv(os.path.join(BASE_DIR, "2_revenue_metrics.csv"))

  cond_file = (
      "3_conditional_behaviour.csv"
      if os.path.exists(os.path.join(BASE_DIR, "3_conditional_behaviour.csv"))
      else "3_conditional_behavior.csv"
  )
  df_cond = pd.read_csv(os.path.join(BASE_DIR, cond_file))

  df_scroll = pd.read_csv(os.path.join(BASE_DIR, "4_scroll_telemetry.csv"))

  if "depth_10_pct" in df_scroll.columns:
    df_scroll = df_scroll.melt(
        id_vars=["arm"],
        value_vars=[
            "depth_10_pct",
            "depth_25_pct",
            "depth_50_pct",
            "depth_75_pct",
            "depth_100_pct",
        ],
        var_name="Depth",
        value_name="Reach_Pct",
    )
    df_scroll["Depth"] = (
        df_scroll["Depth"].str.replace("depth_", "").str.replace("_pct", "%")
    )

  df_device = pd.read_csv(os.path.join(BASE_DIR, "5_device_friction.csv"))

  attr_file = (
      "6_revenue_attribution.csv"
      if os.path.exists(os.path.join(BASE_DIR, "6_revenue_attribution.csv"))
      else "6_revenue_attribution"
  )
  df_attr = pd.read_csv(os.path.join(BASE_DIR, attr_file))

  return df_funnel, df_revenue, df_cond, df_scroll, df_device, df_attr


try:
  df_funnel, df_revenue, df_cond, df_scroll, df_device, df_attr = (
      load_sql_data()
  )
except Exception as e:
  st.error(
      f"Error loading pre-computed SQL CSV outputs. Please ensure all SQL summary"
      f" CSV files exist. Details: {e}"
  )
  st.stop()

arm_map = {"a": "Arm A (Control)", "b": "Arm B (Variant)"}

# -----------------------------------------------------------------------------
# 3. Sidebar — Case Study Details
# -----------------------------------------------------------------------------
with st.sidebar:
  # --- NEW: Load Logo ---
  logo_path = os.path.join(BASE_DIR, "puffy_logo.jpg")
  if os.path.exists(logo_path):
      st.image(logo_path, use_column_width=True)
  
  st.title("📌 Case Study Overview")
  st.markdown("""
    **Project:** Puffy Lux PDP A/B Test  
    **Author:** Nihal Rajeev Sainudeen  
    **Role:** Data Analyst  
    """)
  st.markdown("---")
  st.markdown("### Key Takeaway")
  st.info("""
    **Arm B suffered from UX friction.**
    While Arm B Size Selectors convert well, lower scroll reach led more users to bypass selector interaction entirely, driving down total revenue.
    """)
  st.markdown("---")
  pdf_slot = st.empty()  # placeholder — filled in once charts are built
  st.markdown(
      "[📂 GitHub"
      " Repository](https://github.com/nck320/puffy-data-analyst-case-study)"
  )
# -----------------------------------------------------------------------------
# 4. Executive Header Section
# -----------------------------------------------------------------------------
st.title("🧪 Puffy Lux PDP Redesign — A/B Experiment Analysis")
st.caption(
    "Arm A (Control) vs. Arm B (Variant) Behavioral & Financial Performance"
    " Audit"
)
st.markdown("---")

# -----------------------------------------------------------------------------
# 5. KPI Summary Panel
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
# 6. Core Visualizations Section
# -----------------------------------------------------------------------------
col_left, col_right = st.columns(2)

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
# 7. Scroll Telemetry & Financial Attribution
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

    cr_imp = df_attr["conversion_rate_impact"].values[0]
    aov_imp = df_attr["aov_impact"].values[0]
    tot_delta = df_attr["total_rpu_delta"].values[0]

    fig_water = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=["relative", "relative", "total"],
            x=["Conversion Drop", "AOV Drift", "Net RPU Delta"],
            y=[cr_imp, aov_imp, tot_delta],
            text=[f"${cr_imp:.2f}", f"${aov_imp:.2f}", f"${tot_delta:.2f}"],
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
# 8. Real PDF Export
# -----------------------------------------------------------------------------
def fig_to_image(fig, width=1400, height=820, scale=2):
  """Render a Plotly figure to a high-res transparent PNG for the PDF."""
  png_bytes = fig.to_image(format="png", width=width, height=height, scale=scale)
  return ImageReader(io.BytesIO(png_bytes))


def draw_background(c, width, height):
  c.setFillColor(colors.HexColor("#0E1117"))
  c.rect(0, 0, width, height, fill=1, stroke=0)


def draw_header(c, width, height, title):
  c.setFillColor(colors.HexColor("#3B82F6"))
  c.rect(0, height - 0.72 * inch, width, 0.025 * inch, fill=1, stroke=0)
  c.setFillColor(colors.white)
  c.setFont("Helvetica-Bold", 11)
  c.drawString(0.5 * inch, height - 0.55 * inch, title)
  c.setFillColor(colors.HexColor("#94A3B8"))
  c.setFont("Helvetica", 8)
  c.drawRightString(
      width - 0.5 * inch,
      height - 0.55 * inch,
      "Puffy Lux PDP A/B Test — Nihal Rajeev Sainudeen",
  )


def draw_footer(c, width, margin, page_label):
  c.setFillColor(colors.HexColor("#64748B"))
  c.setFont("Helvetica", 7)
  c.drawString(margin, margin * 0.6, page_label)


def generate_pdf_report(fig_funnel, fig_cond, fig_scroll, fig_water,
                         cr_a, cr_b, rpu_a, rpu_b, logo_path):
  buffer = io.BytesIO()
  c = canvas.Canvas(buffer, pagesize=letter)
  width, height = letter
  margin = 0.5 * inch

  # ---- Page 1: Cover + Key Takeaway + KPIs ----
  draw_background(c, width, height)
  
  # --- Robust Logo Drawing for ReportLab ---
  if os.path.exists(logo_path):
      try:
          # Center the logo nicely at the top of the cover page
          logo_w = 2.2 * inch
          logo_h = 0.8 * inch
          logo_x = (width - logo_w) / 2
          logo_y = height - 1.6 * inch
          c.drawImage(logo_path, logo_x, logo_y, width=logo_w, height=logo_h, preserveAspectRatio=True, mask="auto")
      except Exception as e:
          print(f"Could not render logo in PDF: {e}")

  # Balanced vertical shift for a centered look
  shift_y = 1.0 * inch 

  c.setFillColor(colors.white)
  c.setFont("Helvetica-Bold", 20)
  c.drawString(margin, height - 1.9 * inch - shift_y, "Puffy Lux PDP Redesign")
  c.setFont("Helvetica-Bold", 13)
  c.setFillColor(colors.HexColor("#94A3B8"))
  c.drawString(margin, height - 2.2 * inch - shift_y, "A/B Experiment Intelligence Report")
  c.setFont("Helvetica", 9)
  c.setFillColor(colors.HexColor("#CBD5E1"))
  c.drawString(margin, height - 2.5 * inch - shift_y,
               "Author: Nihal Rajeev Sainudeen   |   Role: Data Analyst")

  box_y = height - 3.7 * inch - shift_y
  box_h = 0.85 * inch
  c.setFillColor(colors.HexColor("#1E293B"))
  c.rect(margin, box_y, width - 2 * margin, box_h, fill=1, stroke=0)
  c.setFillColor(colors.HexColor("#3B82F6"))
  c.rect(margin, box_y, 0.05 * inch, box_h, fill=1, stroke=0)
  c.setFillColor(colors.HexColor("#60A5FA"))
  c.setFont("Helvetica-Bold", 9)
  c.drawString(margin + 0.15 * inch, box_y + box_h - 0.2 * inch, "KEY TAKEAWAY")
  c.setFillColor(colors.HexColor("#E2E8F0"))
  c.setFont("Helvetica", 9)
  ty = box_y + box_h - 0.4 * inch
  for line in [
      "Arm B suffered from UX friction. While Arm B Size Selectors convert",
      "well, lower scroll reach led more users to bypass selector interaction",
      "entirely, driving down total revenue.",
  ]:
    c.drawString(margin + 0.15 * inch, ty, line)
    ty -= 0.16 * inch

  kpis = [
      ("Arm A Conv Rate", f"{cr_a:.2f}%", None),
      ("Arm B Conv Rate", f"{cr_b:.2f}%", f"{cr_b - cr_a:+.2f}%"),
      ("Arm A Rev/User", f"${rpu_a:.2f}", None),
      ("Arm B Rev/User", f"${rpu_b:.2f}", f"-${abs(rpu_b - rpu_a):.2f}"),
  ]
  gap = 0.15 * inch
  card_w = (width - 2 * margin - 3 * gap) / 4
  card_h = 0.9 * inch
  card_y = box_y - card_h - 0.3 * inch
  cx = margin
  for label, value, delta in kpis:
    c.setFillColor(colors.HexColor("#161B22"))
    c.rect(cx, card_y, card_w, card_h, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#A1A1AA"))
    c.setFont("Helvetica-Bold", 7)
    c.drawString(cx + 0.12 * inch, card_y + card_h - 0.22 * inch, label.upper())
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(cx + 0.12 * inch, card_y + card_h - 0.52 * inch, value)
    if delta:
      delta_color = colors.HexColor("#F87171") if delta.strip().startswith("-") else colors.HexColor("#4ADE80")
      c.setFillColor(delta_color)
      c.setFont("Helvetica", 8)
      c.drawString(cx + 0.12 * inch, card_y + 0.14 * inch, delta)
    cx += card_w + gap

  draw_footer(c, width, margin, "Page 1 of 3")
  c.showPage()

  # ---- Page 2: Funnel + Conditional Purchase Rate ----
  draw_background(c, width, height)
  draw_header(c, width, height, "1–2. Engagement Funnel & Conditional Purchase Rate")

  chart_w = width - 2 * margin
  top_offset = 1.05 * inch  
  bottom_offset = 0.4 * inch  
  gap = 0.3 * inch
  chart_h = (height - top_offset - bottom_offset - gap) / 2

  img1 = fig_to_image(fig_funnel)
  c.drawImage(img1, margin, height - top_offset - chart_h,
              width=chart_w, height=chart_h, preserveAspectRatio=True, mask="auto")

  img2 = fig_to_image(fig_cond)
  c.drawImage(img2, margin, height - top_offset - 2 * chart_h - gap,
              width=chart_w, height=chart_h, preserveAspectRatio=True, mask="auto")

  draw_footer(c, width, margin, "Page 2 of 3")
  c.showPage()

  # ---- Page 3: Scroll Telemetry + RPU Waterfall ----
  draw_background(c, width, height)
  draw_header(c, width, height, "3–4. Scroll Telemetry & RPU Loss Attribution")

  img3 = fig_to_image(fig_scroll)
  c.drawImage(img3, margin, height - top_offset - chart_h,
              width=chart_w, height=chart_h, preserveAspectRatio=True, mask="auto")

  img4 = fig_to_image(fig_water)
  c.drawImage(img4, margin, height - top_offset - 2 * chart_h - gap,
              width=chart_w, height=chart_h, preserveAspectRatio=True, mask="auto")

  draw_footer(c, width, margin, "Page 3 of 3")
  c.showPage()

  c.save()
  buffer.seek(0)
  return buffer


with pdf_slot.container():
  if st.button("📄 Generate PDF Report", key="pdf_gen_sql"):
    with st.spinner("Rendering charts to PDF..."):
      pdf_buffer = generate_pdf_report(
          fig_funnel, fig_cond, fig_scroll, fig_water, cr_a, cr_b, rpu_a, rpu_b, logo_path
      )
    st.session_state["pdf_buffer"] = pdf_buffer.getvalue()

  if "pdf_buffer" in st.session_state:
    st.download_button(
        label="⬇️ Download PDF",
        data=st.session_state["pdf_buffer"],
        file_name="Puffy_Lux_PDP_Experiment_Results.pdf",
        mime="application/pdf",
        key="pdf_download_sql",
    )
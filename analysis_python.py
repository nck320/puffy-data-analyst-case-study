import json
import pandas as pd

print("Executing Complete Pure Python/Pandas Pipeline (Analyses 1-6)...")

# ----------------------------------------------------
# Data Ingestion & Preprocessing
# ----------------------------------------------------
events = pd.read_csv("ab_hero_v4_events.csv")
orders = pd.read_csv("ab_hero_v4_order_line_items.csv")


def parse_json_key(data, key):
  try:
    return json.loads(data).get(key)
  except:
    return None


# Extract first arm assignment per user
ab_init = events[events["event_name"] == "ab_experiment_init"].copy()
ab_init["arm"] = ab_init["event_data"].apply(
    lambda x: parse_json_key(x, "experiment_var")
)
ab_init = ab_init.dropna(subset=["arm"]).sort_values("ingestion_timestamp")
user_arms = ab_init.groupby("client_id")["arm"].first().reset_index()

# Filter to valid traffic
df = events.merge(user_arms, on="client_id", how="inner")
valid = df[df["session_traffic_quality"] == "valid"].copy()

totals = valid.groupby("arm")["client_id"].nunique().to_dict()

# ==========================================
# 1. LINEAR FUNNEL
# ==========================================
funnel_list = []
for arm in ["a", "b"]:
  arm_df = valid[valid["arm"] == arm]
  base_u = totals[arm]
  funnel_list.append({
      "arm": arm,
      "base_users": base_u,
      "page_viewed": arm_df[arm_df["event_name"] == "page_viewed"][
          "client_id"
      ].nunique(),
      "size_changed": arm_df[arm_df["event_name"] == "size_changed"][
          "client_id"
      ].nunique(),
      "size_changed_pct": round(
          (
              arm_df[arm_df["event_name"] == "size_changed"][
                  "client_id"
              ].nunique()
              / base_u
          )
          * 100,
          2,
      ),
      "atc": arm_df[arm_df["event_name"] == "product_added_to_cart"][
          "client_id"
      ].nunique(),
      "atc_pct": round(
          (
              arm_df[arm_df["event_name"] == "product_added_to_cart"][
                  "client_id"
              ].nunique()
              / base_u
          )
          * 100,
          2,
      ),
      "checkout_initiated": arm_df[
          arm_df["event_name"] == "checkout_initiated"
      ]["client_id"].nunique(),
      "completed": arm_df[arm_df["event_name"] == "checkout_completed"][
          "client_id"
      ].nunique(),
      "conversion_pct": round(
          (
              arm_df[arm_df["event_name"] == "checkout_completed"][
                  "client_id"
              ].nunique()
              / base_u
          )
          * 100,
          2,
      ),
  })

df_1 = pd.DataFrame(funnel_list)
df_1.to_csv("py_1_linear_funnel.csv", index=False)

# ==========================================
# 2. REVENUE & AOV IMPACT
# ==========================================
cc_events = valid[valid["event_name"] == "checkout_completed"].copy()
cc_events["order_id_parsed"] = cc_events["event_data"].apply(
    lambda x: parse_json_key(x, "order_id")
)
cc_events["order_id_parsed"] = pd.to_numeric(
    cc_events["order_id_parsed"], errors="coerce"
)
cc_orders = cc_events[["client_id", "arm", "order_id_parsed"]].drop_duplicates()

orders_with_arm = orders.merge(
    cc_orders, left_on="order_id", right_on="order_id_parsed", how="inner"
)
order_totals = (
    orders_with_arm.groupby(["order_id", "arm"])["value"].sum().reset_index()
)

rev_list = []
for arm in ["a", "b"]:
  arm_orders = order_totals[order_totals["arm"] == arm]
  base_u = totals[arm]
  tot_rev = arm_orders["value"].sum()
  rev_list.append({
      "arm": arm,
      "base_users": base_u,
      "total_orders": len(arm_orders),
      "avg_order_value_aov": round(arm_orders["value"].mean(), 2),
      "total_revenue": round(tot_rev, 2),
      "revenue_per_user_rpu": round(tot_rev / base_u, 2),
  })

df_2 = pd.DataFrame(rev_list)
df_2.to_csv("py_2_revenue_metrics.csv", index=False)

# ==========================================
# 3. CONDITIONAL BEHAVIOR
# ==========================================
user_flags = (
    valid.groupby(["client_id", "arm"])
    .agg(
        has_sc=("event_name", lambda x: int((x == "size_changed").any())),
        has_atc=(
            "event_name",
            lambda x: int((x == "product_added_to_cart").any()),
        ),
        has_co=(
            "event_name",
            lambda x: int((x == "checkout_completed").any()),
        ),
    )
    .reset_index()
)

cond_list = []
for arm in ["a", "b"]:
  sub = user_flags[user_flags["arm"] == arm]
  for sc_val, segment_name in [(1, "Size Selector"), (0, "Default Bypasser")]:
    seg = sub[sub["has_sc"] == sc_val]
    cond_list.append({
        "arm": arm,
        "user_segment": segment_name,
        "segment_user_count": len(seg),
        "atc_rate_pct": round(seg["has_atc"].mean() * 100, 2),
        "purchase_rate_pct": round(seg["has_co"].mean() * 100, 2),
    })

df_3 = pd.DataFrame(cond_list)
df_3.to_csv("py_3_conditional_behavior.csv", index=False)

# ==========================================
# 4. CUMULATIVE SCROLL REACHABILITY
# ==========================================
scroll_events = valid[valid["event_name"] == "scroll"].copy()
scroll_events["scroll_depth"] = pd.to_numeric(
    scroll_events["event_data"].apply(
        lambda x: parse_json_key(x, "scroll_depth_pct")
    ),
    errors="coerce",
)
user_max_scroll = (
    scroll_events.groupby(["client_id", "arm"])["scroll_depth"]
    .max()
    .reset_index()
)

scroll_list = []
for arm in ["a", "b"]:
  base_u = totals[arm]
  arm_scrolls = user_max_scroll[user_max_scroll["arm"] == arm]
  scroll_list.append({
      "arm": arm,
      "base_users": base_u,
      "depth_10_pct": round(
          ((arm_scrolls["scroll_depth"] >= 10).sum() / base_u) * 100, 2
      ),
      "depth_25_pct": round(
          ((arm_scrolls["scroll_depth"] >= 25).sum() / base_u) * 100, 2
      ),
      "depth_50_pct": round(
          ((arm_scrolls["scroll_depth"] >= 50).sum() / base_u) * 100, 2
      ),
      "depth_75_pct": round(
          ((arm_scrolls["scroll_depth"] >= 75).sum() / base_u) * 100, 2
      ),
      "depth_100_pct": round(
          ((arm_scrolls["scroll_depth"] >= 100).sum() / base_u) * 100, 2
      ),
  })

df_4 = pd.DataFrame(scroll_list)
df_4.to_csv("py_4_scroll_telemetry.csv", index=False)

# ==========================================
# 5. DEVICE FRICTION BREAKDOWN
# ==========================================
device_list = []
for (arm, device), group in valid.groupby(["arm", "device"]):
  tot = group["client_id"].nunique()
  sc_cnt = group[group["event_name"] == "size_changed"]["client_id"].nunique()
  co_cnt = group[group["event_name"] == "checkout_completed"][
      "client_id"
  ].nunique()
  device_list.append({
      "arm": arm,
      "device": device,
      "total_users": tot,
      "size_selectors": sc_cnt,
      "size_selector_pct": round((sc_cnt / tot) * 100, 2),
      "conversion_pct": round((co_cnt / tot) * 100, 2),
  })

df_5 = pd.DataFrame(device_list).sort_values(["device", "arm"])
df_5.to_csv("py_5_device_friction.csv", index=False)

# ==========================================
# 6. REVENUE LOSS ATTRIBUTION (CR vs. AOV)
# ==========================================
cr_a = df_1[df_1["arm"] == "a"]["conversion_pct"].values[0] / 100.0
cr_b = df_1[df_1["arm"] == "b"]["conversion_pct"].values[0] / 100.0

aov_a = df_2[df_2["arm"] == "a"]["avg_order_value_aov"].values[0]
aov_b = df_2[df_2["arm"] == "b"]["avg_order_value_aov"].values[0]

rpu_a = df_2[df_2["arm"] == "a"]["revenue_per_user_rpu"].values[0]
rpu_b = df_2[df_2["arm"] == "b"]["revenue_per_user_rpu"].values[0]

delta_rpu = rpu_b - rpu_a
cr_impact = (cr_b - cr_a) * aov_a
aov_impact = cr_b * (aov_b - aov_a)

df_6 = pd.DataFrame([{
    "arm_a": "a",
    "arm_b": "b",
    "rpu_a": rpu_a,
    "rpu_b": rpu_b,
    "total_rpu_delta": round(delta_rpu, 2),
    "conversion_rate_impact": round(cr_impact, 2),
    "aov_impact": round(aov_impact, 2),
}])

df_6.to_csv("py_6_revenue_attribution.csv", index=False)

print("All 6 Pure Python CSV exports complete!")

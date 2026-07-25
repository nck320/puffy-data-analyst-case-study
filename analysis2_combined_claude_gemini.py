import json
import numpy as np
import pandas as pd
from scipy.stats import chi2, norm

# ==========================================
# 1. LOAD & CLEAN DATA
# ==========================================
print("Loading datasets...")
events = pd.read_csv("ab_hero_v4_events.csv")
orders = pd.read_csv("ab_hero_v4_order_line_items.csv")

# Extract user arm assignment (first assignment per client_id)
ab_init = events[events["event_name"] == "ab_experiment_init"].copy()


def parse_arm(data):
    try:
        return json.loads(data).get("experiment_var")
    except:
        return None


ab_init["arm"] = ab_init["event_data"].apply(parse_arm)
ab_init = ab_init.sort_values("ingestion_timestamp")
user_arms = ab_init.groupby("client_id")["arm"].first().reset_index()

# Merge arms back & filter to valid traffic
df = events.merge(user_arms, on="client_id", how="inner")
valid = df[df["session_traffic_quality"] == "valid"].copy()

# ==========================================
# 2. LINEAR FUNNEL + STATISTICAL Z-TESTS
# ==========================================
funnel_steps = [
    ("page_viewed", "Page Viewed"),
    ("size_changed", "Size Changed"),
    ("product_added_to_cart", "Add to Cart"),
    ("checkout_initiated", "Checkout Initiated"),
    ("checkout_started", "Checkout Started"),
    ("checkout_completed", "Checkout Completed"),
]


def z_test(x1, n1, x2, n2):
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    # Check to prevent division by zero if both x1 and x2 are zero
    if p_pool == 0 or p_pool == 1:
        return p1, p2, 0.0, 1.0
    se = (p_pool * (1 - p_pool) * (1 / n1 + 1 / n2)) ** 0.5
    z = (p1 - p2) / se
    p = 2 * (1 - norm.cdf(abs(z)))
    return p1, p2, z, p


print("\n--- 1. LINEAR FUNNEL & SIGNIFICANCE ---")
a_n = valid[valid["arm"] == "a"]["client_id"].nunique()
b_n = valid[valid["arm"] == "b"]["client_id"].nunique()

for event_code, label in funnel_steps:
    a_cnt = valid[(valid["arm"] == "a") & (valid["event_name"] == event_code)][
        "client_id"
    ].nunique()
    b_cnt = valid[(valid["arm"] == "b") & (valid["event_name"] == event_code)][
        "client_id"
    ].nunique()
    p1, p2, z, p = z_test(a_cnt, a_n, b_cnt, b_n)
    print(
        f"{label:<20} | Arm A: {a_cnt:>4} ({p1*100:>5.1f}%) | Arm B: {b_cnt:>4}"
        f" ({p2*100:>5.1f}%) | Z={z:.2f}, p={p:.4f}"
    )

# ==========================================
# 3. REVENUE & FINANCIAL IMPACT ANALYSIS
# ==========================================
print("\n--- 2. REVENUE & AOV METRICS ---")
cc_events = valid[valid["event_name"] == "checkout_completed"].copy()


def get_order_id(data):
    try:
        return json.loads(data).get("order_id")
    except:
        return None


cc_events["order_id_parsed"] = pd.to_numeric(
    cc_events["event_data"].apply(get_order_id), errors="coerce"
)
orders_with_arm = orders.merge(
    cc_events[["order_id_parsed", "arm", "client_id"]].drop_duplicates(),
    left_on="order_id",
    right_on="order_id_parsed",
    how="inner",
)
order_totals = (
    orders_with_arm.groupby(["order_id", "arm"])["value"].sum().reset_index()
)

for arm_label, base_n in [("a", a_n), ("b", b_n)]:
    ao = order_totals[order_totals["arm"] == arm_label]
    rev = ao["value"].sum()
    rpu = rev / base_n if base_n > 0 else 0
    print(
        f"Arm {arm_label.upper()}: {len(ao)} orders | AOV = ${ao['value'].mean():,.2f}"
        f" | Total Rev = ${rev:,.2f} | RPU = ${rpu:.2f}"
    )

# ==========================================
# 4. CONDITIONAL BEHAVIORAL SEGMENTATION
# ==========================================
print("\n--- 3. CONDITIONAL FUNNEL (SIZE SELECTORS VS. BYPASSERS) ---")
user_summary = (
    valid.groupby(["client_id", "arm"])
    .agg(
        has_sc=("event_name", lambda x: (x == "size_changed").any()),
        has_atc=("event_name", lambda x: (x == "product_added_to_cart").any()),
        has_co=("event_name", lambda x: (x == "checkout_completed").any()),
    )
    .reset_index()
)

for arm in ["a", "b"]:
    sub = user_summary[user_summary["arm"] == arm]
    tot = len(sub)
    selectors = sub[sub["has_sc"]]
    bypassers = sub[~sub["has_sc"]]

    print(f"\nArm {arm.upper()} Behavioral Breakdown:")
    print(
        f"  Size Selectors: {len(selectors)} ({len(selectors)/tot*100:.1f}%) | ATC"
        f" Rate: {selectors['has_atc'].mean()*100:.1f}% | Conversion:"
        f" {selectors['has_co'].mean()*100:.1f}%"
    )
    print(
        f"  Default Bypassers: {len(bypassers)} ({len(bypassers)/tot*100:.1f}%)"
        f" | ATC Rate: {bypassers['has_atc'].mean()*100:.1f}% | Conversion:"
        f" {bypassers['has_co'].mean()*100:.1f}%"
    )

# ==========================================
# 5. DIAGNOSTICS: SCROLL DEPTH & DEVICE SRM
# ==========================================
print("\n--- 4. SCROLL DEPTH & DEVICE SRM DIAGNOSTICS ---")


def parse_scroll(data):
    try:
        return json.loads(data).get("scroll_depth_pct")
    except:
        return None


scroll_df = valid[valid["event_name"] == "scroll"].copy()
if not scroll_df.empty:
    scroll_df["scroll_depth"] = scroll_df["event_data"].apply(parse_scroll)
    # Convert to numeric in case values are string percentages
    scroll_df["scroll_depth"] = pd.to_numeric(
        scroll_df["scroll_depth"], errors="coerce"
    )
    print("Scroll Depth Statistics by Arm:")
    print(scroll_df.groupby("arm")["scroll_depth"].agg(["mean", "median", "std"]))

print("\nDevice Distribution Across Arms (SRM Diagnostic):")
device_users = (
    valid.groupby("client_id")[["arm", "device"]].first().reset_index()
)
print(pd.crosstab(device_users["device"], device_users["arm"]))
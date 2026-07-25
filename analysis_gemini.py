import json
import numpy as np
import pandas as pd
from scipy.stats import chi2, chi2_contingency, norm

# ==========================================
# A. LOAD & CLEAN DATA
# ==========================================
print("Loading datasets...")
events = pd.read_csv('ab_hero_v4_events.csv')
orders = pd.read_csv('ab_hero_v4_order_line_items.csv')

# Extract experiment arm per client_id from ab_experiment_init
ab_init = events[events['event_name'] == 'ab_experiment_init'].copy()


def parse_arm(event_data):
  try:
    return json.loads(event_data).get('experiment_var')
  except:
    return None


ab_init['arm'] = ab_init['event_data'].apply(parse_arm)
ab_init = ab_init.sort_values('ingestion_timestamp')
user_arms = ab_init.groupby('client_id')['arm'].first().reset_index()

# Merge arm back to events and filter valid traffic
df = events.merge(user_arms, on='client_id', how='inner')
valid = df[df['session_traffic_quality'] == 'valid'].copy()

print(
    f"Valid dataset loaded: {len(valid)} events across"
    f" {valid['client_id'].nunique()} unique clients.\n"
)

# ==========================================
# B. LINEAR FUNNEL ANALYSIS
# ==========================================
funnel_steps = [
    ('page_viewed', 'Page Viewed'),
    ('size_changed', 'Size Changed'),
    ('product_added_to_cart', 'Add to Cart'),
    ('checkout_initiated', 'Checkout Initiated'),
    ('checkout_started', 'Checkout Started'),
    ('checkout_completed', 'Checkout Completed'),
]

print("--- 1. LINEAR CONVERSION FUNNEL ---")
funnel_results = {}
for arm in ['a', 'b']:
  arm_data = valid[valid['arm'] == arm]
  total_users = arm_data['client_id'].nunique()
  funnel_results[arm] = {'total': total_users}

  print(f"\nArm {arm.upper()} (Base N = {total_users}):")
  for event_name, label in funnel_steps:
    n_users = arm_data[arm_data['event_name'] == event_name][
        'client_id'
    ].nunique()
    pct = (n_users / total_users) * 100
    funnel_results[arm][event_name] = n_users
    print(f"  {label:<20}: {n_users:>5} ({pct:>5.1f}%)")

# ==========================================
# C. CONDITIONAL / NON-LINEAR FUNNEL
# ==========================================
print("\n--- 2. CONDITIONAL FUNNEL (BEATING CLAUDE) ---")
user_summary = (
    valid.groupby(['client_id', 'arm'])
    .agg(
        has_pv=('event_name', lambda x: (x == 'page_viewed').any()),
        has_sc=('event_name', lambda x: (x == 'size_changed').any()),
        has_atc=('event_name', lambda x: (x == 'product_added_to_cart').any()),
        has_co=(
            'event_name',
            lambda x: (x == 'checkout_completed').any(),
        ),
    )
    .reset_index()
)

for arm in ['a', 'b']:
  sub = user_summary[user_summary['arm'] == arm]
  tot = len(sub)
  selectors = sub[sub['has_sc']]
  bypassers = sub[~sub['has_sc']]

  print(f"\nArm {arm.upper()} Behavioral Segmentation:")
  print(
      f"  Size Selectors: {len(selectors)} ({len(selectors)/tot*100:.1f}% of"
      " users)"
  )
  print(
      f"    └─ ATC Rate: {selectors['has_atc'].mean()*100:.1f}% | Purchaser"
      f" Rate: {selectors['has_co'].mean()*100:.1f}%"
  )
  print(
      f"  Default Bypassers: {len(bypassers)} ({len(bypassers)/tot*100:.1f}% of"
      " users)"
  )
  print(
      f"    └─ ATC Rate: {bypassers['has_atc'].mean()*100:.1f}% | Purchaser"
      f" Rate: {bypassers['has_co'].mean()*100:.1f}%"
  )

# ==========================================
# D. SCROLL TELEMETRY
# ==========================================
print("\n--- 3. SCROLL DEPTH TELEMETRY ---")
scroll_df = valid[valid['event_name'] == 'scroll'].copy()


def parse_scroll_depth(event_data):
  try:
    return json.loads(event_data).get('scroll_depth_pct')
  except:
    return None


scroll_df['scroll_depth'] = scroll_df['event_data'].apply(parse_scroll_depth)
print(scroll_df.groupby('arm')['scroll_depth'].agg(['mean', 'median', 'std']))

# ==========================================
# E. DEVICE BREAKDOWN FOR SRM
# ==========================================
print("\n--- 4. DEVICE BREAKDOWN (SRM DIAGNOSTIC) ---")
device_users = (
    valid.groupby('client_id')[['arm', 'device']].first().reset_index()
)
ct = pd.crosstab(device_users['device'], device_users['arm'])
print(ct)
import duckdb

con = duckdb.connect()

print("Executing Complete DuckDB SQL Pipeline (Queries 1-6)...")

# ==========================================
# QUERY 1: LINEAR FUNNEL
# ==========================================
sql_linear = """
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
    COUNT(DISTINCT CASE WHEN event_name = 'checkout_initiated' THEN client_id END) AS checkout_initiated,
    COUNT(DISTINCT CASE WHEN event_name = 'checkout_completed' THEN client_id END) AS completed,
    ROUND(COUNT(DISTINCT CASE WHEN event_name = 'checkout_completed' THEN client_id END) * 100.0 / t.base_users, 2) AS conversion_pct
FROM valid_events v
JOIN totals t ON v.arm = t.arm
GROUP BY v.arm, t.base_users
ORDER BY v.arm;
"""

# ==========================================
# QUERY 2: REVENUE & AOV IMPACT
# ==========================================
sql_revenue = """
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
"""

# ==========================================
# QUERY 3: CONDITIONAL BEHAVIOR (Selectors vs Bypassers)
# ==========================================
sql_conditional = """
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
"""

# ==========================================
# QUERY 4: CUMULATIVE SCROLL REACHABILITY
# ==========================================
sql_telemetry = """
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
    SELECT 
        client_id, 
        arm,
        MAX(TRY_CAST(json_extract_string(event_data, '$.scroll_depth_pct') AS DOUBLE)) AS max_depth
    FROM valid_events 
    WHERE event_name = 'scroll'
    GROUP BY client_id, arm
),
arm_totals AS (
    SELECT arm, COUNT(DISTINCT client_id) AS base_users FROM valid_events GROUP BY arm
)
SELECT 
    m.arm,
    t.base_users,
    ROUND(COUNT(DISTINCT CASE WHEN max_depth >= 10 THEN m.client_id END) * 100.0 / t.base_users, 2) AS depth_10_pct,
    ROUND(COUNT(DISTINCT CASE WHEN max_depth >= 25 THEN m.client_id END) * 100.0 / t.base_users, 2) AS depth_25_pct,
    ROUND(COUNT(DISTINCT CASE WHEN max_depth >= 50 THEN m.client_id END) * 100.0 / t.base_users, 2) AS depth_50_pct,
    ROUND(COUNT(DISTINCT CASE WHEN max_depth >= 75 THEN m.client_id END) * 100.0 / t.base_users, 2) AS depth_75_pct,
    ROUND(COUNT(DISTINCT CASE WHEN max_depth >= 100 THEN m.client_id END) * 100.0 / t.base_users, 2) AS depth_100_pct
FROM user_max_scroll m
JOIN arm_totals t ON m.arm = t.arm
GROUP BY m.arm, t.base_users
ORDER BY m.arm;
"""

# ==========================================
# QUERY 5: DEVICE FRICTION BREAKDOWN
# ==========================================
sql_device = """
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
    arm,
    device,
    COUNT(DISTINCT client_id) AS total_users,
    COUNT(DISTINCT CASE WHEN event_name = 'size_changed' THEN client_id END) AS size_selectors,
    ROUND(COUNT(DISTINCT CASE WHEN event_name = 'size_changed' THEN client_id END) * 100.0 / COUNT(DISTINCT client_id), 2) AS size_selector_pct,
    ROUND(COUNT(DISTINCT CASE WHEN event_name = 'checkout_completed' THEN client_id END) * 100.0 / COUNT(DISTINCT client_id), 2) AS conversion_pct
FROM valid_events
GROUP BY arm, device
ORDER BY device, arm;
"""

# ==========================================
# QUERY 6: REVENUE LOSS ATTRIBUTION (CR vs. AOV)
# ==========================================
sql_attribution = """
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
        v.arm,
        t.base_users,
        COUNT(v.order_id) AS total_orders,
        COUNT(v.order_id) * 1.0 / t.base_users AS cr,
        AVG(v.order_total) AS aov,
        SUM(v.order_total) / t.base_users AS rpu
    FROM order_vals v
    JOIN totals t ON v.arm = t.arm
    GROUP BY v.arm, t.base_users
)
SELECT 
    a.arm AS arm_a,
    b.arm AS arm_b,
    ROUND(a.rpu, 2) AS rpu_a,
    ROUND(b.rpu, 2) AS rpu_b,
    ROUND(b.rpu - a.rpu, 2) AS total_rpu_delta,
    ROUND((b.cr - a.cr) * a.aov, 2) AS conversion_rate_impact,
    ROUND(b.cr * (b.aov - a.aov), 2) AS aov_impact
FROM arm_metrics a
JOIN arm_metrics b ON a.arm = 'a' AND b.arm = 'b';
"""

# Execute & Export
con.execute(sql_linear).df().to_csv("1_linear_funnel.csv", index=False)
con.execute(sql_revenue).df().to_csv("2_revenue_metrics.csv", index=False)
con.execute(sql_conditional).df().to_csv("3_conditional_behavior.csv", index=False)
con.execute(sql_telemetry).df().to_csv("4_scroll_telemetry.csv", index=False)
con.execute(sql_device).df().to_csv("5_device_friction.csv", index=False)
con.execute(sql_attribution).df().to_csv("6_revenue_attribution.csv", index=False)

print("All 6 DuckDB CSV exports complete!")

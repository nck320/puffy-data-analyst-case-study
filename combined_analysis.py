import duckdb

con = duckdb.connect()

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
    JOIN user_arm u ON e.client_id = u.client_id WHERE u.rn = 1 AND u.arm IS NOT NULL AND e.session_traffic_quality = 'valid'
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
GROUP BY v.arm, t.base_users;
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
    JOIN user_arm u ON e.client_id = u.client_id WHERE u.rn = 1 AND u.arm IS NOT NULL AND e.session_traffic_quality = 'valid'
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
GROUP BY v.arm, t.base_users;
"""

# ==========================================
# QUERY 3: CONDITIONAL BEHAVIOR (Selectors vs. Bypassers)
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
    JOIN user_arm u ON e.client_id = u.client_id WHERE u.rn = 1 AND u.arm IS NOT NULL AND e.session_traffic_quality = 'valid'
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
# QUERY 4: DIAGNOSTIC TELEMETRY (Scroll & Devices)
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
    JOIN user_arm u ON e.client_id = u.client_id WHERE u.rn = 1 AND u.arm IS NOT NULL AND e.session_traffic_quality = 'valid'
),
scroll_data AS (
    SELECT arm, TRY_CAST(json_extract_string(event_data, '$.scroll_depth_pct') AS DOUBLE) AS scroll_depth
    FROM valid_events WHERE event_name = 'scroll'
)
SELECT 
    arm,
    ROUND(AVG(scroll_depth), 2) AS mean_scroll_depth_pct,
    ROUND(MEDIAN(scroll_depth), 2) AS median_scroll_depth_pct,
    ROUND(STDDEV(scroll_depth), 2) AS std_scroll_depth
FROM scroll_data
GROUP BY arm;
"""

# Execute and Export All CSVs
print("Executing Full SQL Pipeline...")

df_1 = con.execute(sql_linear).df()
df_1.to_csv("1_linear_funnel.csv", index=False)
print("1_linear_funnel.csv created!")

df_2 = con.execute(sql_revenue).df()
df_2.to_csv("2_revenue_metrics.csv", index=False)
print("2_revenue_metrics.csv created!")

df_3 = con.execute(sql_conditional).df()
df_3.to_csv("3_conditional_behavior.csv", index=False)
print("3_conditional_behavior.csv created!")

df_4 = con.execute(sql_telemetry).df()
df_4.to_csv("4_scroll_telemetry.csv", index=False)
print("4_scroll_telemetry.csv created!")

print("\nAll 4 CSV exports complete!")
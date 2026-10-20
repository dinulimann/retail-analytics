-- Analysis layer. Materialized views so the dashboard stays fast;
-- refreshed by scripts/load.py after every load.
SET search_path TO retail;

CREATE INDEX ON sales (invoice_date);
CREATE INDEX ON sales (customer_id) WHERE customer_id IS NOT NULL;
CREATE INDEX ON sales (stock_code);

-- Last complete month in the data; December 2011 only has 9 days.
CREATE VIEW period AS
SELECT date_trunc('month', min(invoice_date))::date AS first_month,
       (date_trunc('month', max(invoice_date)) - interval '1 month')::date AS last_full_month
FROM sales;

-- 1. Monthly KPIs (complete months only)
CREATE MATERIALIZED VIEW monthly_kpis AS
SELECT date_trunc('month', s.invoice_date)::date AS month,
       round(sum(s.line_revenue), 0)             AS revenue,
       count(DISTINCT s.invoice)                 AS orders,
       count(DISTINCT s.customer_id)             AS customers,
       round(sum(s.line_revenue) / count(DISTINCT s.invoice), 2) AS avg_order_value
FROM sales s, period p
WHERE s.invoice_date < p.last_full_month + interval '1 month'
GROUP BY 1
ORDER BY 1;

-- 2. Each customer's first purchase month
CREATE MATERIALIZED VIEW customer_first_month AS
SELECT customer_id, date_trunc('month', min(invoice_date))::date AS cohort_month
FROM sales
WHERE customer_id IS NOT NULL
GROUP BY customer_id;

-- 3. New vs returning customers per month (complete months)
CREATE MATERIALIZED VIEW new_vs_returning AS
SELECT date_trunc('month', s.invoice_date)::date AS month,
       count(DISTINCT s.customer_id) FILTER (WHERE f.cohort_month = date_trunc('month', s.invoice_date)) AS new_customers,
       count(DISTINCT s.customer_id) FILTER (WHERE f.cohort_month < date_trunc('month', s.invoice_date)) AS returning_customers,
       round(sum(s.line_revenue) FILTER (WHERE f.cohort_month < date_trunc('month', s.invoice_date)) / sum(s.line_revenue), 3) AS returning_revenue_share
FROM sales s
JOIN customer_first_month f USING (customer_id)
CROSS JOIN period p
WHERE s.invoice_date < p.last_full_month + interval '1 month'
GROUP BY 1
ORDER BY 1;

-- 4. Cohort retention: share of each first-purchase cohort active N months later
CREATE MATERIALIZED VIEW cohort_retention AS
WITH activity AS (
    SELECT DISTINCT s.customer_id, f.cohort_month,
           (extract(year FROM s.invoice_date) - extract(year FROM f.cohort_month)) * 12
         + (extract(month FROM s.invoice_date) - extract(month FROM f.cohort_month)) AS months_since
    FROM sales s
    JOIN customer_first_month f USING (customer_id)
    CROSS JOIN period p
    WHERE s.invoice_date < p.last_full_month + interval '1 month'
), sizes AS (
    SELECT cohort_month, count(*) AS cohort_size FROM customer_first_month GROUP BY 1
)
SELECT a.cohort_month, sz.cohort_size, a.months_since::int AS months_since,
       count(*) AS active_customers,
       round(count(*)::numeric / sz.cohort_size, 3) AS retention
FROM activity a
JOIN sizes sz USING (cohort_month)
GROUP BY a.cohort_month, sz.cohort_size, a.months_since
ORDER BY 1, 3;

-- 5. RFM segmentation, as of the day after the last sale
CREATE MATERIALIZED VIEW rfm AS
WITH base AS (
    SELECT customer_id,
           (SELECT max(invoice_date)::date + 1 FROM sales) - max(invoice_date)::date AS recency_days,
           count(DISTINCT invoice) AS frequency,
           sum(line_revenue)       AS monetary
    FROM sales
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
), scored AS (
    SELECT *,
           6 - ntile(5) OVER (ORDER BY recency_days) AS r,  -- 5 = bought most recently
           ntile(5) OVER (ORDER BY frequency)         AS f,
           ntile(5) OVER (ORDER BY monetary)          AS m
    FROM base
)
SELECT customer_id, recency_days, frequency, round(monetary, 2) AS monetary, r, f, m,
       CASE
           WHEN r >= 4 AND f >= 4                THEN 'Champions'
           WHEN r >= 3 AND f >= 3                THEN 'Loyal'
           WHEN r >= 4 AND f <= 2                THEN 'New / promising'
           WHEN r <= 2 AND f >= 4                THEN 'At risk (were loyal)'
           WHEN r <= 2 AND f BETWEEN 2 AND 3     THEN 'Needs attention'
           WHEN r = 3                            THEN 'Potential'
           ELSE 'Hibernating'
       END AS segment
FROM scored;

CREATE MATERIALIZED VIEW rfm_segments AS
SELECT segment,
       count(*)                         AS customers,
       round(sum(monetary), 0)          AS revenue,
       round(100.0 * sum(monetary) / sum(sum(monetary)) OVER (), 1) AS revenue_pct,
       round(avg(recency_days))         AS avg_recency_days,
       round(avg(frequency), 1)         AS avg_orders
FROM rfm
GROUP BY segment
ORDER BY revenue DESC;

-- 6. Products and countries
CREATE MATERIALIZED VIEW top_products AS
SELECT stock_code,
       mode() WITHIN GROUP (ORDER BY description) AS description,
       sum(quantity)                     AS units,
       round(sum(line_revenue), 0)       AS revenue,
       count(DISTINCT invoice)           AS orders,
       count(DISTINCT customer_id)       AS customers
FROM sales
GROUP BY stock_code
ORDER BY revenue DESC;

CREATE MATERIALIZED VIEW country_summary AS
SELECT country,
       round(sum(line_revenue), 0)   AS revenue,
       count(DISTINCT invoice)       AS orders,
       count(DISTINCT customer_id)   AS customers,
       round(sum(line_revenue) / count(DISTINCT invoice), 2) AS avg_order_value
FROM sales
GROUP BY country
ORDER BY revenue DESC;

-- 7. Market basket: product pairs bought together, among the 150 best sellers
CREATE MATERIALIZED VIEW product_pairs AS
WITH top AS (SELECT stock_code FROM top_products ORDER BY orders DESC LIMIT 150),
lines AS (SELECT DISTINCT invoice, stock_code FROM sales WHERE stock_code IN (SELECT stock_code FROM top)),
n AS (SELECT count(DISTINCT invoice)::numeric AS invoices FROM sales),
support AS (SELECT stock_code, count(*) AS orders FROM lines GROUP BY 1)
SELECT a.stock_code AS product_a, b.stock_code AS product_b,
       count(*) AS orders_together,
       round(count(*) / n.invoices, 4) AS support,
       round(count(*)::numeric / sa.orders, 3) AS confidence_a_to_b,
       round((count(*) / n.invoices) / ((sa.orders / n.invoices) * (sb.orders / n.invoices)), 1) AS lift
FROM lines a
JOIN lines b ON a.invoice = b.invoice AND a.stock_code < b.stock_code
JOIN support sa ON sa.stock_code = a.stock_code
JOIN support sb ON sb.stock_code = b.stock_code
CROSS JOIN n
GROUP BY a.stock_code, b.stock_code, n.invoices, sa.orders, sb.orders
HAVING count(*) >= 300
ORDER BY lift DESC;

-- 8. When people order: weekday x hour
CREATE MATERIALIZED VIEW order_timing AS
SELECT extract(isodow FROM first_line)::int AS weekday,   -- 1 = Monday
       to_char(first_line, 'Dy')            AS weekday_name,
       extract(hour FROM first_line)::int   AS hour,
       count(*)                             AS orders
FROM (SELECT invoice, min(invoice_date) AS first_line FROM sales GROUP BY invoice) o
GROUP BY 1, 2, 3
ORDER BY 1, 3;

-- 9. Cancellations relative to sales, per month
CREATE MATERIALIZED VIEW cancellation_rate AS
SELECT m.month,
       round(m.sales_value, 0)  AS sales_value,
       round(coalesce(c.cancelled_value, 0), 0) AS cancelled_value,
       round(coalesce(c.cancelled_value, 0) / m.sales_value, 3) AS cancelled_share
FROM (SELECT date_trunc('month', invoice_date)::date AS month, sum(line_revenue) AS sales_value FROM sales GROUP BY 1) m
LEFT JOIN (SELECT date_trunc('month', invoice_date)::date AS month, sum(-quantity * unit_price) AS cancelled_value
           FROM cancellations GROUP BY 1) c USING (month)
CROSS JOIN period p
WHERE m.month <= p.last_full_month
ORDER BY 1;

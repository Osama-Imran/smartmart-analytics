-- Indexes and reporting views. Portable across SQLite and PostgreSQL (Supabase).
-- Statements are split on the semicolon character, so comments must not contain it.

CREATE UNIQUE INDEX IF NOT EXISTS ux_products_id ON products (product_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_customers_id ON customers (customer_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_stores_id ON stores (store_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_date ON dim_date (date);
CREATE UNIQUE INDEX IF NOT EXISTS ux_tx_id ON transactions (transaction_id);
CREATE INDEX IF NOT EXISTS ix_tx_date ON transactions (date);
CREATE INDEX IF NOT EXISTS ix_tx_customer ON transactions (customer_id);

-- Fact view: one row per transaction, joined to every dimension, with money columns.
-- revenue = quantity * unit_price * (1 - discount)   cost = quantity * unit_cost
CREATE VIEW v_sales AS
SELECT
    t.transaction_id,
    t.date,
    d.year, d.quarter, d.month, d.month_name, d.year_month, d.day_of_week, d.is_weekend,
    t.customer_id,
    c.name AS customer_name,
    t.product_id,
    p.product_name,
    p.category,
    t.store_id,
    s.store_name,
    s.city,
    s.region,
    s.channel,
    t.quantity,
    t.discount,
    t.payment_method,
    t.quantity * p.unit_price * (1 - t.discount) AS revenue,
    t.quantity * p.unit_cost AS cost,
    t.quantity * p.unit_price * (1 - t.discount) - t.quantity * p.unit_cost AS profit
FROM transactions t
JOIN products p ON p.product_id = t.product_id
JOIN stores s ON s.store_id = t.store_id
JOIN dim_date d ON d.date = t.date
LEFT JOIN customers c ON c.customer_id = t.customer_id;

-- First purchase and lifetime totals per identified customer (guests excluded).
CREATE VIEW v_customer_first AS
SELECT
    customer_id,
    MIN(date) AS first_date,
    MIN(year_month) AS first_year_month,
    COUNT(DISTINCT transaction_id) AS lifetime_orders,
    SUM(revenue) AS lifetime_revenue
FROM v_sales
WHERE customer_id IS NOT NULL
GROUP BY customer_id;

-- Customer table with spend tier. Top 20 percent = High, next 40 percent = Medium, rest = Low.
CREATE VIEW v_customer_summary AS
WITH ranked AS (
    SELECT
        f.customer_id,
        f.first_date,
        f.lifetime_orders AS orders,
        f.lifetime_revenue AS total_spend,
        PERCENT_RANK() OVER (ORDER BY f.lifetime_revenue) AS pr
    FROM v_customer_first f
)
SELECT
    r.customer_id,
    c.name,
    c.city,
    c.region,
    r.first_date,
    r.orders,
    r.total_spend,
    CASE WHEN r.pr >= 0.8 THEN 'High' WHEN r.pr >= 0.4 THEN 'Medium' ELSE 'Low' END AS spend_tier,
    CASE WHEN r.orders >= 2 THEN 'Repeat' ELSE 'One-time' END AS buyer_type
FROM ranked r
JOIN customers c ON c.customer_id = r.customer_id;

CREATE VIEW v_product_summary AS
SELECT
    product_id,
    product_name,
    category,
    SUM(quantity) AS units,
    COUNT(DISTINCT transaction_id) AS orders,
    SUM(revenue) AS revenue,
    SUM(profit) AS profit
FROM v_sales
GROUP BY product_id, product_name, category;

CREATE VIEW v_region_summary AS
SELECT
    region,
    city,
    channel,
    COUNT(DISTINCT transaction_id) AS orders,
    SUM(revenue) AS revenue,
    SUM(profit) AS profit
FROM v_sales
GROUP BY region, city, channel;

CREATE VIEW v_monthly_sales AS
SELECT
    year_month,
    COUNT(DISTINCT transaction_id) AS orders,
    SUM(revenue) AS revenue,
    SUM(profit) AS profit,
    COUNT(DISTINCT customer_id) AS active_customers
FROM v_sales
GROUP BY year_month;

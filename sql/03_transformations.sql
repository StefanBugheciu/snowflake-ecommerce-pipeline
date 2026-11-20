-- This dataset has one product line per order, so each row is also one order.
CREATE VIEW IF NOT EXISTS ECOMMERCE_DB.ANALYTICS.ORDER_DETAILS AS
SELECT
    o.order_id,
    o.order_date,
    o.customer_id,
    c.customer_name,
    c.city,
    o.product_id,
    p.product_name,
    p.category,
    o.quantity,
    o.unit_price_at_sale,
    o.quantity * o.unit_price_at_sale AS order_revenue
FROM ECOMMERCE_DB.RAW.ORDERS AS o
JOIN ECOMMERCE_DB.RAW.CUSTOMERS AS c ON o.customer_id = c.customer_id
JOIN ECOMMERCE_DB.RAW.PRODUCTS AS p ON o.product_id = p.product_id;

CREATE VIEW IF NOT EXISTS ECOMMERCE_DB.ANALYTICS.MONTHLY_REVENUE AS
SELECT DATE_TRUNC('month', order_date) AS order_month,
       COUNT(*) AS order_count,
       SUM(order_revenue) AS revenue
FROM ECOMMERCE_DB.ANALYTICS.ORDER_DETAILS
GROUP BY DATE_TRUNC('month', order_date);

CREATE VIEW IF NOT EXISTS ECOMMERCE_DB.ANALYTICS.PRODUCT_SALES AS
SELECT product_id, product_name,
       COUNT(*) AS order_count,
       SUM(quantity) AS units_sold,
       SUM(order_revenue) AS revenue
FROM ECOMMERCE_DB.ANALYTICS.ORDER_DETAILS
GROUP BY product_id, product_name;

CREATE VIEW IF NOT EXISTS ECOMMERCE_DB.ANALYTICS.CITY_REVENUE AS
SELECT city, COUNT(*) AS order_count, SUM(order_revenue) AS revenue
FROM ECOMMERCE_DB.ANALYTICS.ORDER_DETAILS
GROUP BY city;

CREATE VIEW IF NOT EXISTS ECOMMERCE_DB.ANALYTICS.CUSTOMER_SPENDING AS
SELECT c.customer_id, c.customer_name,
       COUNT(o.order_id) AS order_count,
       COALESCE(SUM(o.order_revenue), 0) AS revenue
FROM ECOMMERCE_DB.RAW.CUSTOMERS AS c
LEFT JOIN ECOMMERCE_DB.ANALYTICS.ORDER_DETAILS AS o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.customer_name;

CREATE VIEW IF NOT EXISTS ECOMMERCE_DB.ANALYTICS.CATEGORY_ORDERS AS
SELECT category, COUNT(*) AS order_count, SUM(order_revenue) AS revenue
FROM ECOMMERCE_DB.ANALYTICS.ORDER_DETAILS
GROUP BY category;

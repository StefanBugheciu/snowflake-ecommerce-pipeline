-- How much revenue did each calendar month bring in?
SELECT order_month, order_count, revenue
FROM ECOMMERCE_DB.ANALYTICS.MONTHLY_REVENUE
ORDER BY order_month;

-- Rank products by units sold. Tied products share a rank.
WITH ranked_products AS (
    SELECT product_id, product_name, units_sold, revenue,
           DENSE_RANK() OVER (ORDER BY units_sold DESC) AS sales_rank
    FROM ECOMMERCE_DB.ANALYTICS.PRODUCT_SALES
)
SELECT sales_rank, product_name, units_sold, revenue
FROM ranked_products
WHERE sales_rank <= 3
ORDER BY sales_rank, product_id;

-- Which cities contribute the most revenue?
SELECT city, order_count, revenue
FROM ECOMMERCE_DB.ANALYTICS.CITY_REVENUE
ORDER BY revenue DESC, city;

-- Who are the five highest-spending customers?
SELECT customer_id, customer_name, order_count, revenue
FROM ECOMMERCE_DB.ANALYTICS.CUSTOMER_SPENDING
ORDER BY revenue DESC, customer_id
LIMIT 5;

-- How many orders contain a product in each category?
SELECT category, order_count, revenue
FROM ECOMMERCE_DB.ANALYTICS.CATEGORY_ORDERS
ORDER BY order_count DESC, category;

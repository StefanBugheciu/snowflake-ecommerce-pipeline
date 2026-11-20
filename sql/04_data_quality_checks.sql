-- Each result row compares an observed value with its expected value.
WITH raw_order_totals AS (
    SELECT COUNT(*) AS order_count,
           COALESCE(SUM(quantity), 0) AS units_sold,
           COALESCE(SUM(quantity * unit_price_at_sale), 0) AS revenue
    FROM ECOMMERCE_DB.RAW.ORDERS
),
analytics_totals AS (
    SELECT 'monthly' AS view_name, SUM(order_count) AS order_count, SUM(revenue) AS revenue
    FROM ECOMMERCE_DB.ANALYTICS.MONTHLY_REVENUE
    UNION ALL
    SELECT 'product', SUM(order_count), SUM(revenue)
    FROM ECOMMERCE_DB.ANALYTICS.PRODUCT_SALES
    UNION ALL
    SELECT 'city', SUM(order_count), SUM(revenue)
    FROM ECOMMERCE_DB.ANALYTICS.CITY_REVENUE
    UNION ALL
    SELECT 'customer', SUM(order_count), SUM(revenue)
    FROM ECOMMERCE_DB.ANALYTICS.CUSTOMER_SPENDING
    UNION ALL
    SELECT 'category', SUM(order_count), SUM(revenue)
    FROM ECOMMERCE_DB.ANALYTICS.CATEGORY_ORDERS
),
checks AS (
    SELECT 'customers_rows' AS check_name, COUNT(*) AS observed, 50 AS expected
    FROM ECOMMERCE_DB.RAW.CUSTOMERS
    UNION ALL
    SELECT 'products_rows', COUNT(*), 6 FROM ECOMMERCE_DB.RAW.PRODUCTS
    UNION ALL
    SELECT 'orders_rows', order_count, 500 FROM raw_order_totals
    UNION ALL
    SELECT 'customers_null_rows', COUNT(*), 0 FROM ECOMMERCE_DB.RAW.CUSTOMERS
    WHERE customer_id IS NULL OR customer_name IS NULL OR city IS NULL
    UNION ALL
    SELECT 'products_null_rows', COUNT(*), 0 FROM ECOMMERCE_DB.RAW.PRODUCTS
    WHERE product_id IS NULL OR product_name IS NULL OR category IS NULL OR price IS NULL
    UNION ALL
    SELECT 'orders_null_rows', COUNT(*), 0 FROM ECOMMERCE_DB.RAW.ORDERS
    WHERE order_id IS NULL OR customer_id IS NULL OR product_id IS NULL
       OR quantity IS NULL OR unit_price_at_sale IS NULL OR order_date IS NULL
    UNION ALL
    SELECT 'customers_duplicate_ids', COUNT(customer_id) - COUNT(DISTINCT customer_id), 0
    FROM ECOMMERCE_DB.RAW.CUSTOMERS
    UNION ALL
    SELECT 'products_duplicate_ids', COUNT(product_id) - COUNT(DISTINCT product_id), 0
    FROM ECOMMERCE_DB.RAW.PRODUCTS
    UNION ALL
    SELECT 'orders_duplicate_ids', COUNT(order_id) - COUNT(DISTINCT order_id), 0
    FROM ECOMMERCE_DB.RAW.ORDERS
    UNION ALL
    SELECT 'missing_customer_references', COUNT(*), 0
    FROM ECOMMERCE_DB.RAW.ORDERS AS o
    LEFT JOIN ECOMMERCE_DB.RAW.CUSTOMERS AS c ON o.customer_id = c.customer_id
    WHERE c.customer_id IS NULL
    UNION ALL
    SELECT 'missing_product_references', COUNT(*), 0
    FROM ECOMMERCE_DB.RAW.ORDERS AS o
    LEFT JOIN ECOMMERCE_DB.RAW.PRODUCTS AS p ON o.product_id = p.product_id
    WHERE p.product_id IS NULL
    UNION ALL
    SELECT 'invalid_product_prices', COUNT(*), 0 FROM ECOMMERCE_DB.RAW.PRODUCTS
    WHERE price <= 0
    UNION ALL
    SELECT 'invalid_order_values', COUNT(*), 0 FROM ECOMMERCE_DB.RAW.ORDERS
    WHERE quantity NOT BETWEEN 1 AND 4 OR unit_price_at_sale <= 0
    UNION ALL
    SELECT 'joined_orders', COUNT(*), (SELECT order_count FROM raw_order_totals)
    FROM ECOMMERCE_DB.ANALYTICS.ORDER_DETAILS
    UNION ALL
    SELECT 'product_units', COALESCE(SUM(units_sold), 0), (SELECT units_sold FROM raw_order_totals)
    FROM ECOMMERCE_DB.ANALYTICS.PRODUCT_SALES
    UNION ALL
    SELECT view_name || '_orders', COALESCE(a.order_count, 0), r.order_count
    FROM analytics_totals AS a CROSS JOIN raw_order_totals AS r
    UNION ALL
    SELECT view_name || '_revenue', COALESCE(a.revenue, 0), r.revenue
    FROM analytics_totals AS a CROSS JOIN raw_order_totals AS r
)
SELECT check_name, observed, expected, observed = expected AS passed
FROM checks
ORDER BY check_name;

# Interview Prep

## How do you explain the project end to end?

I generated a reproducible synthetic store dataset in Python, validated three CSVs, and loaded them into Snowflake. SQL joins RAW orders to customer and product details and exposes five analytics views. Before committing a load, the pipeline checks keys and row counts and reconciles revenue back to the files. I also ran the checks and reports independently on the loaded Snowflake data. All 25 checks passed, and the five aggregates reconciled to 500 orders and 932,270.00 in revenue.

## What is a data warehouse, and what is Snowflake?

A data warehouse organizes data for analysis and reporting. Snowflake is a cloud data platform where stored tables and the compute used to query them are separate. In this project, `ECOMMERCE_DB` holds the data and `COMPUTE_WH` supplies compute for loading and analytics.

## What is the difference between a database, a schema, and a virtual warehouse?

A database groups schemas. A schema groups objects such as tables, views, and stages. Here `RAW` holds inputs and `ANALYTICS` holds derived views. A virtual warehouse is the compute cluster that executes queries and loads. Its size and running time affect cost.

## What is a pipeline, and why is this one ELT?

A pipeline is a repeatable sequence that turns inputs into usable outputs. ETL transforms the data before loading it to the target. ELT loads the source data first, then transforms it in the target system. In this project, Python validates the CSVs and Snowflake performs the analytical joins and aggregations after loading.

## Why use Python, and what does a CSV contain?

Python generates inputs with a seeded random generator, validates them, and orchestrates the warehouse session. CSV is a text representation of rows and fields. The header defines the column order for local validation. Snowflake skips the header and applies the named file format when loading values into typed columns.

## How does Python connect to Snowflake?

The connector uses the account identifier and login name to start Snowflake OAuth for local applications. Snowflake handles browser sign-in with the available identity provider. The connector exchanges the authorization code and opens a session with the configured role, warehouse, database, and schema. The project checks those settings with `CURRENT_*` functions.

## What is a stage, and what does COPY INTO do?

A stage is a file location. The internal stage in this project is managed by Snowflake and lasts for one connector session. `PUT` uploads a file to that location. `COPY INTO` then parses that file using a file format and writes rows into a table.

## What is a JOIN? When do you choose INNER JOIN or LEFT JOIN?

A join matches rows across tables by a condition. An inner join keeps matched rows. `ORDER_DETAILS` joins orders to their customer and product on the corresponding IDs. A left join keeps every row from the left side and fills unmatched right-side values with NULL. `CUSTOMER_SPENDING` uses this to report customers with zero orders.

## What do GROUP BY, SUM, and COUNT do here?

`GROUP BY` makes one result group per key. Monthly revenue truncates a date to the first day of its calendar month, groups by that month, and sums order revenue. `COUNT(*)` counts all rows in a group. In customer spending, `COUNT(o.order_id)` excludes the NULL placeholder from a left join for a customer with no orders.

## What are a CTE and a window function?

A CTE is a named query expression within a statement. The product query first uses a CTE to calculate a rank and then filters on that rank. A window function computes across related rows while keeping an output per row. `DENSE_RANK() OVER (ORDER BY units_sold DESC)` gives the same rank to products tied on units sold and leaves no gaps after a tie.

## Which price should a revenue query use?

Multiply `quantity` by `unit_price_at_sale`, which is stored on the order. A later edit to `PRODUCTS.price` leaves historical revenue unchanged. The project tests this by changing catalog prices and checking that the revenue total stays the same.

## How do you handle errors and verify integrity?

Python refuses malformed CSVs, duplicate keys, and missing references before loading. The loader checks status and row counts from `COPY INTO`. The warehouse quality query checks keys, NULLs, orphan references, and totals. Standard Snowflake tables do not enforce primary-key or foreign-key declarations. A warehouse check failure rolls back the payload transaction.

## What happens when the pipeline runs twice?

The initial-load command checks that RAW is empty and refuses to append to populated tables. An explicit refresh replaces the three datasets in one transaction, so repeating the same snapshot preserves the same row counts and totals. The publication lock coordinates concurrent pipeline sessions. Temporary tables and the stage are scoped to each session.

## How could you load only new or updated data?

Use a stable source key and track a reliable watermark, such as the source update timestamp. Land changes in a staging table, deduplicate them, and use `MERGE` to update matching keys and insert missing ones. Define how to handle late arrivals, deletions, and replay before moving away from a full snapshot.

## How could you improve performance and cost?

Start by measuring query profiles, refresh duration, scanned data, and warehouse usage. A small warehouse with auto-suspend is appropriate for this sporadic demo. At a larger scale, compare full refresh against incremental loading and ordinary views against materialized aggregates for the most frequently used reports.

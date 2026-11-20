# Architecture

## Entry points

| Command | Behavior |
| --- | --- |
| `main.py generate` | Build and validate the three CSVs |
| `main.py validate` | Check the current files and print the source revenue total |
| `main.py check-connection` | Connect and verify role, warehouse, database, and schema |
| `main.py analytics` | Run the warehouse quality checks and reports over the current snapshot |
| `main.py run` | Load an initial snapshot and report analytics |
| `main.py run --refresh` | Publish a replacement snapshot for the three project tables |

## Data flow

The CSVs are an extract from a synthetic source. The generator picks a product and copies its price into each order. Local validation uses `Decimal` for money and checks that each order points to an existing product and customer. The loader copies the current files to a private temporary directory and validates the same file copies it uploads. Keep generation and loading separate when working with the same `data/` directory so the loader can take a consistent input snapshot.

The connector session uses `SYSADMIN` and `COMPUTE_WH` in `ECOMMERCE_DB.RAW`. `PUT` sends each binary file stream to a named temporary internal stage. `COPY INTO` parses one file at a time using the named `ECOMMERCE_CSV` format and loads a typed temporary table. The loader checks the upload and copy results. Each session has its own temporary files and tables. [Python Connector API](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-api) [Temporary stages](https://docs.snowflake.com/en/sql-reference/sql/create-stage)

## Publication and recovery

Table, file-format, and view DDL runs outside the transaction because Snowflake DDL implicitly commits an active transaction. The payload transaction starts once all three copies succeed. Updating the single row in `RAW.ECOMMERCE_PIPELINE_STATE` acquires a write lock to serialize publication by pipeline sessions and increments the successful-load count only on commit. External writers to these project tables must follow the same coordination strategy. [Snowflake transactions](https://docs.snowflake.com/en/sql-reference/transactions)

On the first load, the pipeline checks that the target tables are empty and inserts all three copies. With an explicit refresh, it uses `INSERT OVERWRITE` for each target. The row counts and quality checks run before commit, using the candidate RAW rows and the views in the same session. A failed check triggers a rollback. Retrying after a rejected initial load is safe once the cause is resolved. DDL can remain after a failed run. If only the reporting queries fail after publication, the commit remains successful and the reports can be rerun independently. [Snowflake INSERT](https://docs.snowflake.com/en/sql-reference/sql/insert)

## Analytics and scope

The analytics command reads the active warehouse data using the same SQL checks and reports as the load workflow. Its optional create-if-missing flag installs project views while preserving any existing definitions.

`ORDER_DETAILS` stays at order grain. Customer spending uses a left join to keep customers with zero orders. Monthly and city views aggregate revenue, product sales sums units as well as revenue, and category orders counts orders per category. Revenue uses sale prices stored on orders. City and category labels are read from the current customer and product records.

The demo assumes one product per order and uses views over a small synthetic dataset. A multi-product model would separate order headers from lines and define whether category-level order counts count distinct orders or lines. For a larger workload, measure query performance and refresh cost before materializing aggregates or changing warehouse size.

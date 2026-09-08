# Databricks notebook source
# DBTITLE 1,Setup parameter widget
# Create widget to receive the order_id parameter from Task-X
dbutils.widgets.text("var_id", "", "Order ID")

# COMMAND ----------

# DBTITLE 1,Run SQL query with parameter
# Get the parameter value
var_id = dbutils.widgets.get("var_id")

# Run the SQL query with parameter binding
query = """
SELECT *
FROM db_jobs.default.orders
WHERE id = :var_id
"""

result_df = spark.sql(query, args={"var_id": var_id})
display(result_df)

# COMMAND ----------

# DBTITLE 1,Store output for downstream task
# Convert result to format that can be passed to downstream task
rows = result_df.collect()
rows_json = [row.asDict() for row in rows]

# Store as task value for downstream consumption
dbutils.notebook.exit(str(rows_json))

# COMMAND ----------


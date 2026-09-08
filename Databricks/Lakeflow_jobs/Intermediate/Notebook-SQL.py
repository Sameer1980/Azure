# Databricks notebook source
# DBTITLE 1,Cell 1
dbutils.widgets.text("sql_output","")

# COMMAND ----------

# DBTITLE 1,Cell 2
dbutils.widgets.get("sql_output")
# Databricks notebook source
dbutils.widgets.text("records_processed","")

# COMMAND ----------

records_processed = dbutils.widgets.get("records_processed")
records_processed
# Databricks notebook source
df = spark.createDataFrame([("James",40),("Ann",45),("Jeff",35),("Sally",30)],["name","age"])
display(df)

# COMMAND ----------

total_records = df.count()
total_records

# COMMAND ----------

dbutils.jobs.taskValues.set("total_records",total_records)

# COMMAND ----------

order_id = 3
dbutils.jobs.taskValues.set(key="order_id",value=order_id)
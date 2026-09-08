# Databricks notebook source
dbutils.widgets.text("file_name","")

# COMMAND ----------

file_name = dbutils.widgets.get("file_name")

# COMMAND ----------

df = spark.read.format("parquet")\
	                  .load(f"/Volumes/db_jobs/default/raw_data/{file_name}.parquet")
	

# COMMAND ----------

df.write.format("delta")\
       .mode("overwrite")\
       .save(f"/Volumes/db_jobs/default/raw_data/sinkSQL/{file_name}")
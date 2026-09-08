from pyspark import pipelines as dp
from pyspark.sql.functions import sum 

#Creating a MAT BUSINESS VIEW 

@dp.materialized_view(
    name = "business_sales"
)
def business_sales():
    df_fact = spark.read.table("fact_sales").filter("__END_AT IS NULL")
    df_dimCust = spark.read.table("dim_customers_v2")
    df_dimProd = spark.read.table("dim_products_v2")

    df_join = df_fact.join(df_dimCust, df_fact.customer_id == df_dimCust.customer_id, "inner").join(df_dimProd, df_fact.product_id == df_dimProd.product_id, "inner")

    df_prun = df_join.select("region","category","amount")

    df_agg = df_prun.groupBy("region","category").agg(sum("amount").alias("total_sales"))
  
    return df_agg

    
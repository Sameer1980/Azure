from pyspark import pipelines as dp

#Sales Expectations
sales_rules ={
    "rule_1": "sales_id IS NOT NULL"
}

#Empty streaming table
dp.create_streaming_table(
    name = "sales_stg_v2",
    expect_all_or_drop = sales_rules
)

# Creating east sales flow
@dp.append_flow(target="sales_stg_v2")
def east_sales():
    df = spark.readStream.table("dlt_test.source.sales_east")
    return df

# Creating west sales flow
@dp.append_flow(target="sales_stg_v2")
def west_sales():
    df = spark.readStream.table("dlt_test.source.sales_west")
    return df

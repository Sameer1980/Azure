from pyspark import pipelines as dp

#Customers Expectations
customers_rules ={
    "rule_1": "customer_id IS NOT NULL",
    "rule_2": "customer_name IS NOT NULL"
}


#Ingesting customers
@dp.table(
    name="customers_stg_v2"
)

@dp.expect_all_or_drop(customers_rules)
def customers_stg_v2():
    df = spark.readStream.table("dlt_test.source.customers")
    return df

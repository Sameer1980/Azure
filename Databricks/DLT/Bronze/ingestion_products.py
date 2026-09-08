from pyspark import pipelines as dp

#Products Expectations
products_rules ={
    "rule_1": "product_id IS NOT NULL",
    "rule_2": "price >= 0"
}

#Ingesting products
@dp.table(
    name="products_stg_v2"
)

@dp.expect_all(products_rules)
def products_stg_v2():
    df = spark.readStream.table("dlt_test.source.products")
    return df

from pyspark import pipelines as dp
import pyspark.sql.functions as F

#Transforming customers data 
@dp.temporary_view(
    name = "customers_enr_view"
)
def customers_stg_trns():
    df = spark.readStream.table("customers_stg_v2")
    df = df.withColumn("customer_name", F.upper(F.col("customer_name")))
    return df

#Creating Destination Silver Table.
dp.create_streaming_table(
    name = "customers_enriched_v2"
)

dp.create_auto_cdc_flow(
    target = "customers_enriched_v2",
    source = "customers_enr_view",
    keys = ["customer_id"],
    sequence_by = "last_updated",
    ignore_null_updates = False,
    apply_as_deletes = None,
    apply_as_truncates = None,
    column_list = None,
    except_column_list = None,
    stored_as_scd_type = 1,
    track_history_column_list = None,
    track_history_except_column_list = None
)

# Creating a Silver view for Gold layer.


from pyspark import pipelines as dp
import pyspark.sql.functions as F

#Transforming sales data 
@dp.temporary_view(
    name = "sales_enr_view"
)
def sales_stg_trns():
    df = spark.readStream.table("sales_stg_v2")
    return df

#Creating Destination Silver Table.
dp.create_streaming_table(
    name = "sales_enriched_v2"
)

dp.create_auto_cdc_flow(
    target = "sales_enriched_v2",
    source = "sales_enr_view",
    keys = ["sales_id"],
    sequence_by = "sales_timestamp",
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


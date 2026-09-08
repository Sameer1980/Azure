from pyspark import pipelines as dp
import pyspark.sql.functions as F
from pyspark.sql.types import IntegerType

#Transforming products data 
@dp.temporary_view(
    name = "products_enr_view"
)
def products_stg_trns():
    df = spark.readStream.table("products_stg_v2")
    df = df.withColumn("price",F.col("price").cast(IntegerType()))
    return df

#Creating Destination Silver Table.
dp.create_streaming_table(
    name = "products_enriched_v2"
)

dp.create_auto_cdc_flow(
    target = "products_enriched_v2",
    source = "products_enr_view",
    keys = ["product_id"],
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


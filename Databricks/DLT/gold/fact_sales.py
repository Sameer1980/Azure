from pyspark import pipelines as dp

# Create Empty Streaming table 
dp.create_streaming_table(
    name = "fact_sales"
)
# AUTO CDC FLOW
dp.create_auto_cdc_flow(
    target = "fact_sales",
    source = "sales_enr_view",
    keys = ["sales_id"],
    sequence_by = "sales_timestamp",
    ignore_null_updates = False,
    apply_as_deletes = None,
    apply_as_truncates = None,
    column_list = None,
    except_column_list = None,
    stored_as_scd_type = 2,
    track_history_column_list = None,
    track_history_except_column_list = None
)

## This file implements the same logic in python as the SQL version
## 
## SETUP REQUIRED:
## 1. Create the volume: CREATE VOLUME main.dbdemos_sdp_cdc_python.raw_data
## 2. Upload your CDC data folders (e.g., customers/, transactions/) to the volume
## 3. Each folder should contain JSON files with CDC format
##

from pyspark import pipelines as dp
from pyspark.sql.functions import *


# -------------------------------------------------------------------
# --- 1. Ingest data with autoloader: loop on all folders -----------
# -------------------------------------------------------------------
# Let's loop over all the folders and dynamically generate our SDP pipeline.

# Helper function to safely get config with default value
def get_conf(key, default):
    try:
        return spark.conf.get(key)
    except:
        return default

catalog = get_conf("catalog", "main")
schema = get_conf("schema", "dbdemos_sdp_cdc_python")

volume_path = f"/Volumes/{catalog}/{schema}/raw_data"

def create_pipeline(table_name):
    print(f"Building SDP CDC pipeline for {table_name}")

    ##Raw CDC Table
    # Schema hints to ensure id and customer_id are read as strings
    schema_hints = {
        "customers": "id string, customer_id string",
        "transactions": "id string, customer_id string"
    }
    
    @dp.table(
        name=table_name + "_cdc",
        comment=f"New {table_name} data incrementally ingested from cloud object storage landing zone",
    )
    def raw_cdc():
        reader = (
            spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "json")
            .option("cloudFiles.inferColumnTypes", "true")
            .option("cloudFiles.partitionColumns", "")  # No partition columns
        )
        
        # Add schema hints if available for this table
        if table_name in schema_hints:
            reader = reader.option("cloudFiles.schemaHints", schema_hints[table_name])
        
        return reader.load(f"/Volumes/{catalog}/{schema}/raw_data/" + table_name)

    ##Clean CDC input and track quality with expectations
    @dp.temporary_view(
        name=table_name + "_cdc_clean",
        comment="Cleansed cdc data, tracking data quality with a view. We ensude valid JSON, id and operation type",
    )
    @dp.expect_or_drop("no_rescued_data", "_rescued_data IS NULL")
    @dp.expect_or_drop("valid_id", "id IS NOT NULL")
    @dp.expect_or_drop("valid_operation", "operation IN ('APPEND', 'DELETE', 'UPDATE')")
    def raw_cdc_clean():
        return spark.readStream.table(table_name + "_cdc")

    ##Materialize the final table
    dp.create_streaming_table(name=table_name, comment="Clean, materialized " + table_name)
    dp.create_auto_cdc_flow(
        target=table_name,  # The customer table being materilized
        source=table_name + "_cdc_clean",  # the incoming CDC
        keys=["id"],  # what we'll be using to match the rows to upsert
        sequence_by=col("operation_date"),  # we deduplicate by operation date getting the most recent value
        ignore_null_updates=False,
        apply_as_deletes=expr("operation = 'DELETE'"),  # DELETE condition
        except_column_list=["operation", "operation_date", "_rescued_data"], # in addition we drop metadata columns
    )

# Check if volume exists and create tables dynamically
tables_created = []
try:
    folders = dbutils.fs.ls(volume_path)
    if not folders:
        raise ValueError(f"Volume {volume_path} exists but is empty. Please add data folders.")
    
    print(f"Found {len(folders)} folder(s) in {volume_path}")
    for folder in folders:
        table_name = folder.name[:-1]  # Remove trailing slash
        print(f"Creating pipeline for table: {table_name}")
        create_pipeline(table_name)
        tables_created.append(table_name)
    print(f"Successfully created {len(tables_created)} table pipeline(s): {', '.join(tables_created)}")
    
except Exception as e:
    error_msg = str(e)
    if "UC_VOLUME_NOT_FOUND" in error_msg or "does not exist" in error_msg:
        # Volume doesn't exist - provide clear setup instructions
        print("=" * 80)
        print("ERROR: Required volume not found!")
        print("=" * 80)
        print(f"\nThe volume '{volume_path}' does not exist.")
        print(f"\nTo set up this pipeline, run the following SQL command:")
        print(f"\n  CREATE VOLUME {catalog}.{schema}.raw_data;")
        print(f"\nThen upload your CDC data folders to the volume.")
        print(f"Each folder (e.g., 'customers/', 'transactions/') should contain JSON files.")
        print("=" * 80)
        raise RuntimeError(
            f"Volume {volume_path} not found. "
            f"Create it with: CREATE VOLUME {catalog}.{schema}.raw_data"
        )
    else:
        # Different error - re-raise with context
        print(f"Error accessing volume {volume_path}: {error_msg}")
        raise


# ---------------------------------------------------------------
# --- -- Slowly Changing Dimension of type 2 (SCD2) -------------
# ---------------------------------------------------------------

# Only create SCD2 if customers table was created
if "customers" in tables_created:
    # create the table
    dp.create_streaming_table(
        name="SCD2_customers", comment="Slowly Changing Dimension Type 2 for customers"
    )

    # store all changes as SCD2
    dp.create_auto_cdc_flow(
        target="SCD2_customers",
        source="customers_cdc_clean",
        keys=["id"],
        sequence_by=col("operation_date"),
        ignore_null_updates=False,
        apply_as_deletes=expr("operation = 'DELETE'"),
        except_column_list=["operation", "operation_date", "_rescued_data"],
        stored_as_scd_type="2",
    )  # Enable SCD2 and store individual updates
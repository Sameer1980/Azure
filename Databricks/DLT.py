/*3 major components of DLT :
- Streaming table .- Streaming data handles incremental data as well in microbatches.
- Materialized View  
- Views - Two types of views are used - Batch views and streaming views.
*/


from pyspark import pipelines as dp
from pyspark.sql import functions as F

# Simple example streaming table
@dp.table(
    comment="Example streaming table with generated data"
)
def bronze_events():
    """Streaming table with sample generated data."""
    return (
        spark.readStream
        .format("rate")
        .option("rowsPerSecond", 1)
        .load()
        .select(
            F.col("value").alias("event_id"),
            F.current_timestamp().alias("event_time")
        )
    )

# Materialized view aggregating the streaming data
@dp.materialized_view(
    comment="Aggregated view of events"
)
def gold_event_summary():
    """Materialized view showing event counts."""
    return (
        spark.read.table("bronze_events")
        .groupBy(F.window("event_time", "1 minute"))
        .agg(F.count("*").alias("event_count"))
    )

This is a valid PySpark structured streaming function that generates continuous dummy data for testing. 
It uses the built-in rate source to produce a constant stream of incrementing numbers and timestamps.

#Key Components
#.format("rate"): A special data source used for testing that generates a sequential value column (Long type) and a timestamp column.
#.option("rowsPerSecond", 1): Throttles the stream to generate exactly one new row every second.
#F.col("value").alias("event_id"): Renames the default auto-incremented number to a more descriptive domain ID.
#F.current_timestamp(): Adds the exact execution time of the processing micro-batch.



This defines a Databricks materialized view named gold_event_summary:

#@dp.materialized_view(...) registers the function as a materialized view with a description.
#spark.read.table("bronze_events") reads the source events table.
#.groupBy(F.window("event_time", "1 minute")) groups events into one-minute time windows based on event_time.
#.agg(F.count("*").alias("event_count")) counts events in each window and names the result event_count.
#The returned view will contain the window boundaries and the corresponding event count.

-- ---------------------------------------
-- 1/ Ingesting data with Autoloader
-- ---------------------------------------
CREATE OR REFRESH STREAMING TABLE customers_cdc
COMMENT "New customer data incrementally ingested from cloud object storage landing zone"
AS SELECT *
FROM STREAM read_files(
  "/Volumes/main/dbdemos_sdp_cdc/raw_data/customers",
  format => "json",
  inferColumnTypes => true
);

-- --------------------------------------------------
-- 2/ Cleanup & expectations to track data quality
-- --------------------------------------------------
-- this could also be a VIEW
CREATE OR REFRESH STREAMING TABLE customers_cdc_clean(
  CONSTRAINT valid_id EXPECT (id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_operation EXPECT (operation IN ('APPEND', 'DELETE', 'UPDATE')) ON VIOLATION DROP ROW,
  CONSTRAINT valid_json_schema EXPECT (_rescued_data IS NULL) ON VIOLATION DROP ROW
)
COMMENT "Cleansed cdc data, tracking data quality with a view. We ensude valid JSON, id and operation type"
AS SELECT * 
FROM STREAM(customers_cdc);

-- ---------------------------------------------------------
-- 3/ Materializing the silver table with APPLY CHANGES
-- ---------------------------------------------------------

CREATE OR REFRESH STREAMING TABLE customers
  COMMENT "Clean, materialized customers";

CREATE FLOW customers_cdc_flow AS
AUTO CDC INTO customers
FROM stream(customers_cdc_clean)
KEYS (id)
APPLY AS DELETE WHEN operation = "DELETE"
SEQUENCE BY operation_date --primary key, auto-incrementing ID of any kind that can be used to identity order of events, or timestamp
COLUMNS * EXCEPT (operation, operation_date, _rescued_data)
STORED AS SCD TYPE 1;
  -- -----------------------------------------------------
  -- 4/ Slowly Changing Dimension of type 2 (SCD2)
  -- -----------------------------------------------------
  -- create the table
CREATE OR REFRESH STREAMING TABLE SCD2_customers
  COMMENT "Slowly Changing Dimension Type 2 for customers";

-- store all changes as SCD2
CREATE FLOW SCD2_customers_cdc_flow AS
AUTO CDC INTO SCD2_customers
FROM stream(customers_cdc_clean)
KEYS (id)
APPLY AS DELETE WHEN operation = "DELETE"
SEQUENCE BY operation_date
COLUMNS * EXCEPT (operation, operation_date, _rescued_data)
STORED AS SCD TYPE 2;

Pipeline Breakdown:
1.CREATE FLOW customers_cdc_flow: Declares and names your streaming ingestion pipeline.
2.AUTO CDC INTO customers: Automatically handles incoming inserts, updates, and deletes to update the target dimension table.
3.FROM stream(customers_cdc_clean): Consumes the source data as an append-only, continuous stream of changes.
4.KEYS (id): Defines the primary key used to match incoming records against existing rows in the target table.
5.APPLY AS DELETE WHEN...: Logic that tells the engine to physically or logically remove the record when a source delete event occurs.
6.SEQUENCE BY operation_date: Resolves out-of-order data by ensuring only the record with the latest timestamp or ID is applied.
7.COLUMNS * EXCEPT...: Drops the metadata columns used for CDC processing so they do not clutter your final production table.
8.STORED AS SCD TYPE 1: Overwrites existing records with new data, keeping no historical tracking of changes.


The actual pipeline name and the create flow name are different because they operate at two completely different levels of the 
Databricks architecture: the infrastructure/management level versus the data processing/execution level.
 1.Pipeline Name (The Container / Management Level)
 What it is: The pipeline name (often configured in the Databricks UI or Lakeflow pipelines settings) identifies the entire infrastructure resource, cluster configuration,
 storage location, and orchestration job.
 Scope: It is global to your workspace or job scheduler. It manages the execution environment, compute resources, and overall scheduling of your code files.
 2. Flow Name (The Execution / Dataset Level)
 What it is: A flow name defined via commands like CREATE FLOW or Python decorators (@append_flow) specifies an individual unit of data processing work inside that pipeline.
 Scope: It is local to the data transformation logic. A single pipeline can contain multiple independent flows writing to different streaming tables or 
 merging multiple sources into a single target table. 
 Databricks uses the specific flow name to track internal state and streaming checkpoints.

## This file implements the same logic in python as the SQL version
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

Code Breakdown:
1.@dp.table(...): This is a Python decorator from the Delta Live Tables framework (dp). It tells Databricks to create or update a managed Delta table using the function below it.
2.name=table_name + "_cdc": Sets the name of the destination table by appending _cdc to a variable named table_name.
3.comment=...: Adds a descriptive note to the table explaining that it contains new, incrementally ingested data from the cloud storage landing zone.
4.def raw_cdc():: Defines the function that returns the Spark DataFrame, which DLT uses to populate the table.

The Spark DataStream Reader:
1) (spark.readStream).format("cloudFiles"): Uses Databricks Auto Loader (cloudFiles), which automatically and efficiently detects and processes new files as they arrive in cloud storage.
2) .option("cloudFiles.format", "json"): Tells Auto Loader that the incoming files are in JSON format.
3) .option("cloudFiles.inferColumnTypes", "true"): Automatically detects the data types of the JSON fields (like strings, integers, or timestamps) without needing a 
predefined schema.
4) .option("cloudFiles.partitionColumns", ""): Specifies that the data is not partitioned upon ingestion (or leaves it open for default handling). Note: In actual execution, 
this option usually expects a comma-separated list or is omitted if there are no partitions.

@dp.expect_or_drop: This decorator drops any record from the target dataset that fails the validation condition.
no_rescued_data: Drops records where the _rescued_data column is not null (ensuring no schema mismatch/malformed data issues).
valid_id: Drops records where the id column is null.
valid_operation: Drops records where the operation column is not one of the allowed values: APPEND, DELETE, or UPDATE.
spark.readStream.table(...): Reads a streaming Delta table using the combined table_name and _cdc suffix.

# Create source table:
# dlt_test -> source -> orders
CREATE TABLE orders
(
    order_id INT,
    order_date DATE,
    customer_id INT,
    order_status STRING
);

INSERT INTO orders
VALUES
    (1, '2023-01-01', 101, 'SHIPPED'),
    (2, '2023-01-02', 102, 'PENDING'),
    (3, '2023-01-03', 103, 'COMPLETE'),
    (4, '2023-01-04', 104, 'CANCELLLED'),
    (5, '2023-01-05', 105, 'COMPLETE');


# Store the below code in a ETL pipeline file.'core_components.py'

import dlt

# Creating streaming table.
@dlt.table(
    name = "first_stream_table"
)
def first_stream_table():
    df = spark.readStream.table("dlt_test.source.orders")
    return df
    

# The dataframe reads data from "dlt_test.source.orders" table and returns it to the decorator which converts it to a streaming table "first_stream_table".

# Two types of views in DLT -> a) Batch Views , b) Streaming Views . 

# Create materialzed view.
@dlt.table(
    name = "first_mat_view"
)

def first_mat_view():
    df = spark.read.table("dlt_test.source.orders")
    return df
    
    
 # Create batch view 
@dlt.view(
    name = "first_batch_view"
)
def first_batch_view():
    df = spark.read.table("dlt_test.source.orders")
    return df

# Create streaming view 
@dlt.view(
    name = "first_stream_view"
)
def first_stream_view():
    df = spark.readStream.table("dlt_test.source.orders")
    return df

# Create another ETL file '2_dependency.py'.
""" Creating a end-to-end simple, basic pipeline """ 

                    |------25---------|
|              |--->|first_mat_view   |
|-----------|  |    |---------------- |
|10 source1 |
|-----------|       |-------------------|
|           |  |--->|      15           |
|15 source2 |       |first_stream_table |
|-----------|       |-------------------|

 
 # if the source has got two tables - source1 (10 rows) and source2 (15 rows) :
 # first_mat_view will have 25 rows loaded.
 # first_stream_table will only have 15 rows loaded because this is streaming , incremental table.
 
 import dlt 
 
 """ Creating an end-to-end Basic Pipeline """
 # Staging area 
@dlt.table(
    name = "staging_orders"
)
def staging_orders():
    df = spark.readStream.table("dlt_test.source.orders")
    return df

#Creating Transformed Area
@dlt.view(
    name = "transformed_orders"
)
def transformed_orders():
    df = spark.readStream.table("staging_orders")
    return df

# A dependency gets created :- staging_orders --> transformed_tables
# To do some transformations use the exploration sample file , 

# In 2_dependency.py file 
import dlt 
import pyspark.sql.functions as F

"""
Creating an end-to-end Basic pipeline
"""
# Staging area 
@dlt.table(
    name = "staging_orders"
)
def staging_orders():
    df = spark.readStream.table("dlt_test.source.orders")
    return df

#Creating Transformed Area
@dlt.view(
    name = "transformed_orders"
)
def transformed_orders():
    df = spark.readStream.table("staging_orders")
    df = df.withColumn("order_status", F.lower(F.col("order_status")))
    return df

#Creating Aggregated Area

@dlt.table(
    name = "aggregated_orders"
    )
def aggregated_orders():
    df = spark.readStream.table("transformed_orders")
    df = df.groupBy("order_status").count()
    return df 

# Another dependency gets created :- staging_orders --> transformed_tables --> aggregated_orders

#Streaming tables can work with append only sources.
------------------------------------------------------------------------------------------------------------------------------------------------------------------|
# Real world project - DDL - PIPELINE NAME -> 'transformation_sourcecode_v2'
#BRONZE
------------------------------------------------------------------------------------------------------------------------------------------------------------------|
#Create east table
CREATE TABLE sales_east
(
    sales_id INT PRIMARY KEY,
    customer_id INT,
    product_id INT,
    quantity INT,
    amount DECIMAL(10,2),
    sales_timestamp TIMESTAMP
);
#Insert 1 (initial load)
INSERT INTO sales_east VALUES
(1,101,201,2,200.00,'2025-08-01 10:00:00'),
(2,102,202,2,120.00,'2025-08-01 10:05:00'),
(3,103,203,2,500.00,'2025-08-01 10:10:00'),
(4,104,204,2,330.00,'2025-08-01 10:15:00'),
(5,105,205,2,440.00,'2025-08-01 10:20:00');

#Insert 2 (Incremental load) - - To be run later for validation
INSERT INTO sales_east VALUES
(6,106,206,1,100.00,'2025-08-02 09:00:00'),
(7,107,207,2,250.00,'2025-08-02 09:15:00');
------------------------------------------------------------------------------------------------------------------------------------------------------------------|
# Create west table
CREATE TABLE sales_west
(
    sales_id INT PRIMARY KEY,
    customer_id INT,
    product_id INT,
    quantity INT,
    amount DECIMAL(10,2),
    sales_timestamp TIMESTAMP
);
#Insert1 (initial load)
INSERT INTO sales_west VALUES
(8,108,201,1,150.00,'2025-08-01 11:00:00'),
(9,109,202,2,260.00,'2025-08-01 11:05:00'),
(10,110,203,3,390.00,'2025-08-01 11:10:00'),
(11,111,204,1,130.00,'2025-08-01 11:15:00'),
(12,112,205,4,560.00,'2025-08-01 11:20:00');

# Incremental load - To be run later for validation
    INSERT INTO sales_west VALUES
    (13,113,206,2,300.00,'2025-08-02 09:30:00'),
    (14,114,207,1,130.00,'2025-08-02 09:35:00');


-------------------------------------------------------------------------------------------------------------=======================================================|
#Create products table
CREATE TABLE products
(
    product_id INT PRIMARY KEY,
    product_name VARCHAR(100),
    category VARCHAR(50),
    price DECIMAL(10,2),
    last_updated TIMESTAMP
);

#Insert1 (Initial Load)
INSERT INTO products VALUES
(201,'Laptop','Electronics',1000.00,'2025-07-31 12:00:00'),
(202,'Phone','Electronics',120.00,'2025-07-31 12:05:00'),
(203,'Monitor','Electronics',100.00,'2025-07-31 12:10:00'),
(204,'Chair','Furniture',110.00,'2025-07-31 12:15:00'),
(205,'Desk','Furniture',150.00,'2025-07-31 12:20:00'),
(206,'Mouse','Electronics',50.00,'2025-07-31 12:25:00'),
(207,'Keyboard','Electronics',60.00,'2025-07-31 12:30:00'),
(208,'Lamp','Furniture',130.00,'2025-07-31 12:35:00'),
(209,'Router','Electronics',130.00,'2025-07-31 12:40:00'),
(210,'Table','Furniture',130.00,'2025-07-31 12:45:00'),
(211,'Notebook','Stationary',140.00,'2025-07-31 12:50:00'),
(212,'Pen','Stationary',150.00,'2025-07-31 12:55:00');

-- Incremental Load 



---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
#Create customers table
CREATE TABLE customers(
    customer_id INT PRIMARY KEY,
    customer_name VARCHAR(100),
    region VARCHAR(50),
    last_updated TIMESTAMP
);

#Insert1 (Initial Load)
INSERT INTO customers VALUES 
(101,'Alice','East','2025-07-31 13:00:00'),
(102,'Bob','East','2025-07-31 13:05:00'),
(103,'Charlie','East','2025-07-31 13:10:00'),
(104,'Diana','East','2025-07-31 13:15:00'),
(105,'Ethan','East','2025-07-31 13:20:00'),
(106,'Fiona','East','2025-07-31 13:25:00'),
(107,'George','West','2025-07-31 13:30:00'),
(108,'Hannah','West','2025-07-31 13:35:00'),
(109,'Ian','West','2025-07-31 13:40:00'),
(110,'Jane','West','2025-07-31 13:45:00'),
(111,'Kevin','West','2025-07-31 13:50:00'),
(112,'Laura','West','2025-07-31 13:55:00');

 
 # Data model 
 
 |-------------------                           |
 |--------------------SOURCE EAST --------------|              |---------------------|
                                                | APPEND FLOW  |                   
 |------------------                            |------------->| EMPTY STREAM TABLE 
 |-------------------SOURCE WEST ---------------|              | --------------------|
 
 # Create a empty streaming table  and an 'Append-Flow' that reads data from 2 source tables.. table1-> "dlt_test.source.sales_east"
 #and table2-> "dlt_test.source.sales_west"
 #Filename :- "Ingestion_sales.py"
 import dlt
 
#Sales Expectations
sales_rules ={
    "rule_1":"sales_id IS NOT NULL"

#Empty streaming table
dlt.create_streaming_table(
    name = "sales_stg",
    expect_all_or_drop = sales_rules
)

# Creating east sales flow
@dlt.append_flow(target="sales_stg")
def east_sales():

    df = spark.readStream.table("dlt_test.source.sales_east")
    return df

# Creating west sales flow
@dlt.append_flow(target="sales_stg")
def west_sales():

    df = spark.readStream.table("dlt_test.source.sales_west")
    return df
 
--------------------------------------------------------------------------------------------------------------------------------------------------------------------|  
 #Create another file:- "ingestion_products.py"
import dlt
#Ingesting products
@dlt.table(
    name="products_stg"
)

def products_stg():
    df = spark.readStream.table("dlt_test.source.products")
    return df

---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
#Create another file:-    "ingestion_customers.py" 
@dlt.table(
    name="customers_stg"
)

def products_stg():
    df = spark.readStream.table("dlt_test.source.customers")
    return df
---------------------------------------------------------------------------------------------------------------------------------------------------------------------|    
# Expectations - Pass a dictionary of expectations or DQ check rules to the tables.
# In the "ingestion_customers.py" 
import dlt

#Customers Expectations
customers_rules ={
    "rule_1": "customer_id IS NOT NULL",
    "rule_2": "customer_name IS NOT NULL"
}

#Ingesting products
@dlt.table(
    name="customers_stg"
)

@dlt.expect_all_or_drop(customers_rules)
def customers_stg():
    df = spark.readStream.table("dlt_test.source.customers")
    return df
   
   
 # In the "ingestion_products.py"
 import dlt

#Products Expectations
products_rules ={
    "rule_1": "product_id IS NOT NULL",
    "rule_2": "price >= 0"
}

#Ingesting products
@dlt.table(
    name="products_stg"
)

@dlt.expect_all(products_rules)
def products_stg():
    df = spark.readStream.table("dlt_test.source.products")
    return df
------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
#SILVER
------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
# Upsert - It will match the table keys between the source and the target (Bronze -> Silver) and if the keys match it will simply update the target table else it will do an
# insert.

# Here we will implement Auto-CDC.Instead of creating 'Append-Flow' we will be creating a 'Auto-CDC-flow' .

# SEQUENCE_BY parameter in the 'AUTO-CDC' flow . Between the source and the target tables it simply pickup the new value and updates the data in the target table or
# inserts if the data is not there.

#EXCEPT_COLUMN_LIST parameter . So if there are certain fields in the source which we do not want to propagate to the downstream target tables we can use this parameter.

#Type 1 tables are also known as 'upserted tables'.

# Create a new folder SILVER .
------------------------------------------------------------------------|
#Under this folder create a file named "transform_sales.py"
------------------------------------------------------------------------|
import dlt
import pyspark.sql.functions as F
from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

# Reference the Bronze table as a view in this pipeline's DAG
@dlt.view()
def sales_stg():
    return spark.readStream.table("workspace.default.sales_stg")

@dlt.view(
    name = "sales_enr_view"
)
def sales_stg_trns():
    df = spark.readStream.table("sales_stg")
    df = df.withColumn("total_amount",F.col("quantity") * F.col("amount") )
    return df

#Creating destination silver table.
dlt.create_streaming_table(
    name = "sales_enriched"
)

dlt.create_auto_cdc_flow(
    target = "sales_enriched",
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
------------------------------------------------------------------------------------------------|
#Create another file named "transform_products.py"
------------------------------------------------------------------------------------------------|
import dlt
import pyspark.sql.functions as F
from pyspark.sql import SparkSession
from pyspark.sql.types import *

spark = SparkSession.builder.getOrCreate()
# Reference the Bronze table as a view in this pipeline's DAG
@dlt.view()
def products_stg():
    return spark.readStream.table("workspace.default.products_stg")

#Transforming products data 
@dlt.view(
    name = "products_enr_view"
)
def products_stg_trns():
    df = spark.readStream.table("products_stg")
    df = df.withColumn("price",F.col("price").cast(IntegerType()))
    return df

#Creating Destination Silver Table.
dlt.create_streaming_table(
    name = "products_enriched"
)

dlt.create_auto_cdc_flow(
    target = "products_enriched",
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
------------------------------------------------------------------------------------------------|
#Create a third file named "transform_customers.py"
------------------------------------------------------------------------------------------------|
import dlt
import pyspark.sql.functions as F
from pyspark.sql import SparkSession
from pyspark.sql.types import *

spark = SparkSession.builder.getOrCreate()
# Reference the Bronze table as a view in this pipeline's DAG
@dlt.view()
def customers_stg():
    return spark.readStream.table("workspace.default.customers_stg")

#Transforming products data 
@dlt.view(
    name = "customers_enr_view"
)
def products_stg_trns():
    df = spark.readStream.table("customers_stg")
    df = df.withColumn("customer_name", F.upper(F.col("customer_name")))
    return df

#Creating Destination Silver Table.
dlt.create_streaming_table(
    name = "customers_enriched"
)

dlt.create_auto_cdc_flow(
    target = "customers_enriched",
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

===========================================================================================================================================================|
#GOLD
===========================================================================================================================================================|
# We will be creating a SCD 2 type table .
# We have two Dimensions ("customers_stg" & "products_stg") and one Fact table("sales_stg").
# In order to create a slowly changing dimension we use something called as "Auto-CDC Flow".
# We will be using enriched View as our source and not enriched Table because enriched table can be appended or changed and in order to work with 
# streaming tables we can only work with append only sources.

# Create a file named "dim_products.py"
from pyspark import pipelines as dp

# Create Empty Streaming table 
dp.create_streaming_table(
    name = "dim_products"
)

import dlt

# AUTO CDC FLOW
dlt.create_auto_cdc_flow(
    target = "dim_products",
    source = "products_enr_view",
    keys = ["product_id"],
    sequence_by = "last_updated",
    ignore_null_updates = False,
    apply_as_deletes = None,
    apply_as_truncates = None,
    column_list = None,
    except_column_list = None,
    stored_as_scd_type = 2,
    track_history_column_list = None,
    track_history_except_column_list = None
)
# Clone the "dim.products.py" file to create another file "dim_customers.py" .
from pyspark import pipelines as dp


# Create Empty Streaming table 
dp.create_streaming_table(
    name = "dim_customers_v2"
)
# AUTO CDC FLOW
dp.create_auto_cdc_flow(
    target = "dim_customers_v2",
    source = "customers_enr_view",
    keys = ["customer_id"],
    sequence_by = "last_updated",
    ignore_null_updates = False,
    apply_as_deletes = None,
    apply_as_truncates = None,
    column_list = None,
    except_column_list = None,
    stored_as_scd_type = 2,
    track_history_column_list = None,
    track_history_except_column_list = None
)
# Clone the "dim.customers.py" file to create another file "fact_sales.py" .
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
# Create another file named "business_sales.py" 
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


#Model validation 
--------------------------------------
   # 1. Run two incremental inserts for validation .
    
    INSERT INTO sales_east VALUES
(6,106,206,1,100.00,'2025-08-02 09:00:00'),
(7,107,207,2,250.00,'2025-08-02 09:15:00');

INSERT INTO sales_west VALUES
    (13,113,206,2,300.00,'2025-08-02 09:30:00'),
    (14,114,207,1,130.00,'2025-08-02 09:35:00');
    
    #2.Now incremental inserts for SCD products table.
    # Price change for product_id 203
    INSERT INTO products VALUES
    (203,'Monitor','Electronics',90.00,'2025-08-02 08:00:00');
    
    # Name change for product_id 208 
    INSERT INTO products VALUES
    (208,'Desk Lamp','Furniture',130.00,'2025-08-02 08:10:00');
    
    #3. Incremental inserts for customer 103 .
    INSERT INTO customers VALUES 
    (103,'Charlie','Central','2025-08-02 08:30:00');
    
    # Name correction for customer 107.
    INSERT INTO customers VALUES 
    (107,'George Smith','West','2025-08-02 08:40:00');
    
select * from dim_products_v2 where product_id in (208,203);

select * from business_sales;

#Monitor Table Metrics for each table after the pipeline run . For eg: 'customers_stg_v2' there were two expectations and both were met 
#as indicated by the 'Table Metrics'. 

# You can also 'Add Notifications' for pipeline failure or success and set email Ids that will be notified in case of success or failure.
    
# NOTE : We can embed our pipeline inside a Databricks job.    


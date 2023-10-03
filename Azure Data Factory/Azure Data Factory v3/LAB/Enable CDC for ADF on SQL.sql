--//Change database
USE [AdventureWorksLT]
GO

--Check the status of CDC for Database
SELECT [name], is_cdc_enabled from sys.databases

--Check the status of CDC for tables
SELECT [name], is_tracked_by_cdc from sys.tables

--//Enable CDC for database
EXEC sys.sp_cdc_enable_db  
GO  

--//Enable CDC for Table
EXEC sys.sp_cdc_enable_table  
	@source_schema = N'dbo',  
	@source_name   = N'src_customers',  
	@role_name     = NULL,  
	@supports_net_changes = 1  
GO  

--=============================================
--//Disable CDC on Database
EXEC sys.sp_cdc_disable_db  
GO 

--//Disable CDC for Table
EXEC sys.sp_cdc_disable_table  
	@source_schema = N'dbo',  
	@source_name   = N'src_customers',  
	@capture_instance = N'dbo_src_customers'  
GO  

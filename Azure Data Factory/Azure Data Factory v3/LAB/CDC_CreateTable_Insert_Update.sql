--//Create table source customers
--drop table src_customers;
create table src_customers 
(
	customer_id int, 
	first_name varchar(50), 
	last_name varchar(50), 
	email varchar(100), 
	city varchar(50), 
	CONSTRAINT [PK_Customers_001] PRIMARY KEY CLUSTERED ([customer_id]) 
 );

 --//Create Target Table
 --drop table tgt_customers;
create table tgt_customers 
(
	customer_id int, 
	first_name varchar(50), 
	last_name varchar(50), 
	email varchar(100), 
	city varchar(50), 
	CONSTRAINT [PK_Customers_0034] PRIMARY KEY CLUSTERED ([customer_id])
 );


 --//InsertData
 insert into src_customers (customer_id, first_name, last_name, email, city) values 
(1, 'Chevy', 'Leward', 'cleward0@mapy.cz', 'Reading'),
(2, 'Sayre', 'Ateggart', 'sateggart1@nih.gov', 'Portsmouth'),
(3, 'Nathalia', 'Seckom', 'nseckom2@blogger.com', 'Portsmouth');

--//Additional Actions
insert into src_customers (customer_id, first_name, last_name, email, city) values 
(4, 'Farlie', 'Hadigate', 'fhadigate3@zdnet.com', 'Reading'),
(5, 'Anet', 'MacColm', 'amaccolm4@yellowbook.com', 'Portsmouth'),
(6, 'Elonore', 'Bearham', 'ebearham5@ebay.co.uk', 'Portsmouth');

--//Update the customer
update src_customers set first_name='Elon' where customer_id=6;

--//Delete the customer
delete from src_customers where customer_id=5;
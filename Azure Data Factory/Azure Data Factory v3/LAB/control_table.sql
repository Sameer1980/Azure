create table control_table(
	sql_query varchar(8000)
	,region varchar(100)
)

insert into control_table values ('select * from CustomerSalesDataSets where address_region = ''central''', 'central')
insert into control_table values ('select * from CustomerSalesDataSets where address_region = ''East''','east')
insert into control_table values ('select * from CustomerSalesDataSets where address_region = ''South''', 'south')
insert into control_table values ('select * from CustomerSalesDataSets where address_region = ''West''', 'west')
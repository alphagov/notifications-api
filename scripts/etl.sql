-- create a temp table, an intermediate step to transform data from notifications table to the format in ft_billing
-- Note: to run this script successfully, all templates need to be set.

drop table if exists notifications_temp;

--create type notification_type as enum('email', 'sms', 'letter');

create table notifications_temp (
	notification_id uuid,
	dm_datetime date,
	template uuid,
	service uuid,
	annual_billing uuid,
	notification_type varchar,
	provider varchar,
	rate_multiplier numeric,
	crown varchar,
	rate numeric,
	international bool,
	billable_units numeric,
	notifications_sent numeric
);


insert into notifications_temp (notification_id, dm_datetime, template, service, annual_billing, notification_type,
provider, rate_multiplier, crown, rate, international, billable_units, notifications_sent)
select
n.id,
da.bst_date,
n.template_id,
n.service_id,
a.id,
n.notification_type,
coalesce(n.rate_multiplier,1),
s.crown,
coalesce((select rates.rate from rates
where n.notification_type = rates.notification_type and n.sent_at > rates.valid_from order by rates.valid_from desc limit 1), 0),
n.sent_by,
coalesce(n.international, false),
n.billable_units,
1
from public.notification_history n
left join dm_template t on t.template_id = n.template_id
left join dm_datetime da on n.created_at > da.utc_daytime_start and n.created_at < da.utc_daytime_end
left join service s on s.service_id = n.service_id
left join annual_billing a on a.service_id = n.service_id and a.financial_year_start = da.financial_year;

update notifications_temp n set rate = (select rate from letter_rates l where n.rate_multiplier = l.sheet_count and n.crown = l.crown)
where notification_type = 'letter'

-- ft_billing:  Aggregate into billing fact table

delete from ft_billing where 1=1;   -- Note: delete this if we are already using ft_billing

insert into ft_billing (dm_service_year, dm_template, dm_datetime, notification_type, crown, provider, rate_multiplier,
provider_rate, client_rate, international, notifications_sent, billable_units)
select billing.dm_service_year, template.template_id, date.bst_date, billing.notification_type, billing.crown, billing.provider,
avg(billing.rate_multiplier), avg(billing.provider_rate), avg(client_rate), international,
count(*) as notifications_sent,
sum(billing.billable_units) as billable_units
from notifications_temp as billing
left join dm_template template on billing.dm_template = template.template_id
left join dm_datetime date on billing.dm_datetime = date.bst_date
group by date.bst_date, template.template_id, billing.dm_service_year, billing.provider, billing.notification_type, billing.international, billing.crown
order by date.bst_date;

-- update ft_billing set billing_total=billable_units*rate_multiplier*client_rate where 1=1;

update ft_billing set provider='DVLA' where notification_type = 'letter';

update dm_service_year set organisation='Not set' where organisation = null;

update dm_service_year set organisation_type='Not set' where organisation_type = NULL;
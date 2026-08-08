-- migrate:up

ALTER TABLE public.kpi_history
ADD COLUMN report_period integer;

-- migrate:down

ALTER TABLE public.kpi_history
DROP COLUMN report_period;

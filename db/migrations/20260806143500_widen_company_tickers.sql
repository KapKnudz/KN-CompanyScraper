-- migrate:up

ALTER TABLE public.companies
ALTER COLUMN ticker TYPE character varying(20);

-- migrate:down

ALTER TABLE public.companies
ALTER COLUMN ticker TYPE character varying(10);

-- migrate:up

ALTER TABLE companies
    ADD COLUMN sector_id integer,
    ADD COLUMN branch_id integer;

CREATE TABLE kpi_snapshot_history (
    company_id integer NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    kpi_id integer NOT NULL,
    observation_date date NOT NULL DEFAULT CURRENT_DATE,
    value numeric,
    fetched_at timestamp with time zone NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, kpi_id, observation_date)
);

-- migrate:down

DROP TABLE IF EXISTS kpi_snapshot_history;

ALTER TABLE companies
    DROP COLUMN branch_id,
    DROP COLUMN sector_id;

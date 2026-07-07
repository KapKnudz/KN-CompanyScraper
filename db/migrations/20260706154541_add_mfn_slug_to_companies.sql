-- migrate:up

ALTER TABLE companies
ADD COLUMN mfn_slug TEXT UNIQUE;

-- migrate:down

ALTER TABLE companies
DROP COLUMN mfn_slug;
-- migrate:up

UPDATE companies
SET mfn_slug = 'avtech-sweden'
WHERE ticker = 'AVT B';

-- migrate:down

UPDATE companies
SET mfn_slug = NULL
WHERE ticker = 'AVT B';

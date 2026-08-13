-- migrate:up
UPDATE companies
SET mfn_slug = 'byggpartnergruppen'
WHERE ticker = 'BYGGP';

UPDATE companies
SET mfn_slug = 'scandic-hotels-group'
WHERE ticker = 'SHOT';

-- migrate:down
UPDATE companies
SET mfn_slug = NULL
WHERE ticker IN ('BYGGP', 'SHOT');

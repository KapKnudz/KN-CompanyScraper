-- migrate:up
ALTER TABLE ranking_challenger_performance_evaluations
    DROP CONSTRAINT ranking_challenger_performanc_challenger_snapshot_id_horizo_key;

ALTER TABLE ranking_challenger_performance_evaluations
    ADD UNIQUE (challenger_snapshot_id, horizon_months, policy_version);

-- migrate:down
ALTER TABLE ranking_challenger_performance_evaluations
    DROP CONSTRAINT ranking_challenger_performanc_challenger_snapshot_id_horizo_key;

ALTER TABLE ranking_challenger_performance_evaluations
    ADD UNIQUE (challenger_snapshot_id, horizon_months);

-- migrate:up
CREATE TABLE benchmark_prices (
    series_code     TEXT NOT NULL,
    price_date      DATE NOT NULL,
    close           NUMERIC(18, 6) NOT NULL CHECK (close > 0),
    return_basis    TEXT NOT NULL CHECK (
        return_basis IN ('price_return', 'gross_total_return', 'net_total_return')
    ),
    source          TEXT NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (series_code, price_date)
);

CREATE TABLE ranking_performance_evaluations (
    id                  BIGSERIAL PRIMARY KEY,
    ranking_run_id      INTEGER NOT NULL REFERENCES ranking_runs(id) ON DELETE CASCADE,
    horizon_months      INTEGER NOT NULL CHECK (horizon_months > 0),
    target_date         DATE NOT NULL,
    status              TEXT NOT NULL CHECK (
        status IN ('pending', 'complete', 'insufficient_membership')
    ),
    policy_version      TEXT NOT NULL,
    result              JSONB NOT NULL,
    evaluated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ranking_run_id, horizon_months)
);

CREATE INDEX idx_ranking_performance_status_target
    ON ranking_performance_evaluations (status, target_date);

WITH monthly_membership AS (
    SELECT
        monthly.id,
        COALESCE(
            (
                SELECT jsonb_agg((entry.item->>'company_id')::INTEGER ORDER BY entry.ordinality)
                FROM jsonb_array_elements(monthly.scores)
                    WITH ORDINALITY AS entry(item, ordinality)
                WHERE COALESCE((entry.item->>'actionable')::BOOLEAN, FALSE)
            ),
            '[]'::JSONB
        ) AS final_actionable_ids,
        COALESCE(
            (
                SELECT jsonb_agg((entry.item->>'company_id')::INTEGER ORDER BY entry.ordinality)
                FROM jsonb_array_elements(monthly.scores)
                    WITH ORDINALITY AS entry(item, ordinality)
            ),
            '[]'::JSONB
        ) AS final_ranked_ids,
        (
            SELECT deterministic.id
            FROM ranking_runs AS deterministic
            WHERE deterministic.snapshot_month IS NULL
              AND deterministic.run_at <= monthly.run_at
              AND COALESCE(
                  deterministic.inputs_summary->>'ranking_type', ''
              ) <> 'combined_forward_scenario'
            ORDER BY deterministic.run_at DESC, deterministic.id DESC
            LIMIT 1
        ) AS deterministic_run_id
    FROM ranking_runs AS monthly
    WHERE monthly.snapshot_month IS NOT NULL
), frozen_membership AS (
    SELECT
        membership.*,
        COALESCE(
            (
                SELECT jsonb_agg(eligible.company_id ORDER BY eligible.ordinality)
                FROM (
                    SELECT
                        (entry.item->>'company_id')::INTEGER AS company_id,
                        entry.ordinality
                    FROM ranking_runs AS deterministic
                    CROSS JOIN LATERAL jsonb_array_elements(deterministic.scores)
                        WITH ORDINALITY AS entry(item, ordinality)
                    WHERE deterministic.id = membership.deterministic_run_id
                      AND COALESCE(
                          (entry.item->>'rank_eligible')::BOOLEAN,
                          FALSE
                      )
                    ORDER BY entry.ordinality
                    LIMIT 30
                ) AS eligible
            ),
            '[]'::JSONB
        ) AS deterministic_shortlist_ids
    FROM monthly_membership AS membership
)
UPDATE ranking_runs AS monthly
SET inputs_summary = COALESCE(monthly.inputs_summary, '{}'::JSONB) ||
    jsonb_build_object(
        'final_actionable_company_ids', frozen.final_actionable_ids,
        'final_ranked_company_ids', frozen.final_ranked_ids,
        'deterministic_run_id', frozen.deterministic_run_id,
        'deterministic_shortlist_company_ids', frozen.deterministic_shortlist_ids
    )
FROM frozen_membership AS frozen
WHERE monthly.id = frozen.id
  AND NOT (
      COALESCE(monthly.inputs_summary, '{}'::JSONB) ?
      'final_actionable_company_ids'
  );

-- migrate:down
DROP TABLE IF EXISTS ranking_performance_evaluations;
DROP TABLE IF EXISTS benchmark_prices;

-- migrate:up
WITH latest_accepted AS (
    SELECT DISTINCT ON (company_id)
        id,
        company_id,
        content::jsonb AS content,
        created_by,
        metadata,
        created_at
    FROM analysis
    WHERE analysis_type = 'stock_analysis'
      AND metadata->>'validation_status' = 'accepted'
    ORDER BY company_id, created_at DESC, id DESC
)
INSERT INTO company_thesis_revisions (
    company_id,
    revision,
    previous_revision_id,
    source_analysis_id,
    change_type,
    evidence_as_of,
    confidence,
    confidence_limitations,
    content,
    created_by,
    metadata,
    created_at
)
SELECT
    company_id,
    1,
    NULL,
    id,
    'initial',
    CASE
        WHEN metadata->>'evidence_as_of' ~ '^\d{4}-\d{2}-\d{2}$'
            THEN (metadata->>'evidence_as_of')::date
        ELSE NULL
    END,
    CASE
        WHEN content->>'confidence' IN ('low', 'medium', 'high')
            THEN content->>'confidence'
        ELSE 'low'
    END,
    '{}',
    content,
    COALESCE(created_by, 'legacy-analysis'),
    COALESCE(metadata, '{}'::jsonb) || '{"thesis_backfill": true}'::jsonb,
    created_at
FROM latest_accepted
ON CONFLICT (source_analysis_id) DO NOTHING;

-- migrate:down
DELETE FROM company_thesis_revisions
WHERE revision = 1
  AND previous_revision_id IS NULL
  AND metadata->>'thesis_backfill' = 'true';

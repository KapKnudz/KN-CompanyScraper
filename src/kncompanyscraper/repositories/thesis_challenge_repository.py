from dataclasses import asdict

from psycopg2.extras import Json, RealDictCursor

from kncompanyscraper.database import get_connection


class ThesisChallengeRepository:
    def save(
        self,
        *,
        thesis_revision_id: int,
        company_id: int,
        question: str,
        origin: str,
        result,
        created_by: str,
        metadata: dict,
    ) -> int:
        status = "upheld" if result.verdict == "survives" else "open"
        content = {"result": asdict(result), "metadata": metadata}
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO thesis_challenges (
                        company_id, thesis_revision_id, question, challenged_claim,
                        origin, severity, verdict, status, content, created_by,
                        resolved_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            CASE WHEN %s = 'upheld' THEN NOW() ELSE NULL END)
                    RETURNING id
                    """,
                    (
                        company_id,
                        thesis_revision_id,
                        question.strip(),
                        result.challenged_claim,
                        origin,
                        result.severity,
                        result.verdict,
                        status,
                        Json(content),
                        created_by,
                        status,
                    ),
                )
                return cur.fetchone()[0]

    def unresolved_high_company_ids(self) -> set[int]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT company_id
                    FROM thesis_challenges
                    WHERE status = 'open' AND severity = 'high'
                    """
                )
                return {row[0] for row in cur.fetchall()}

    def resolve(self, challenge_id: int, status: str, note: str) -> None:
        if status not in {"upheld", "revised", "rejected"}:
            raise ValueError("challenge resolution must be upheld, revised, or rejected")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE thesis_challenges
                    SET status = %s, resolution_note = %s, resolved_at = NOW()
                    WHERE id = %s AND status = 'open'
                    """,
                    (status, note.strip(), challenge_id),
                )
                if cur.rowcount != 1:
                    raise ValueError("open thesis challenge not found")

    def attach_response_attempt(self, challenge_id: int, raw_analysis_id: int) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE thesis_challenges
                    SET response_raw_analysis_id = %s
                    WHERE id = %s
                      AND status = 'open'
                      AND response_raw_analysis_id IS NULL
                    """,
                    (raw_analysis_id, challenge_id),
                )
                if cur.rowcount != 1:
                    raise ValueError("open thesis challenge already has a response")

    def resolve_with_response(
        self,
        challenge_id: int,
        status: str,
        note: str,
        analysis_id: int,
    ) -> None:
        if status not in {"upheld", "revised"}:
            raise ValueError("analyst response must resolve as upheld or revised")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE thesis_challenges AS challenge
                    SET status = %s,
                        resolution_note = %s,
                        response_analysis_id = %s,
                        response_thesis_revision_id = response_revision.id,
                        resolved_at = NOW()
                    FROM company_thesis_revisions AS response_revision
                    WHERE challenge.id = %s
                      AND challenge.status = 'open'
                      AND response_revision.source_analysis_id = %s
                      AND response_revision.company_id = challenge.company_id
                      AND response_revision.previous_revision_id =
                          challenge.thesis_revision_id
                    """,
                    (status, note.strip(), analysis_id, challenge_id, analysis_id),
                )
                if cur.rowcount != 1:
                    raise ValueError(
                        "open thesis challenge or linked response revision not found"
                    )

    def get(self, challenge_id: int) -> dict | None:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM thesis_challenges WHERE id = %s", (challenge_id,))
                row = cur.fetchone()
                return dict(row) if row else None

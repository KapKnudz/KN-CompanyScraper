from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from kncompanyscraper.repositories.dividend_repository import DividendRepository


def connection_with_cursor(cursor):
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn


def test_get_reviews_uses_stable_event_key():
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "ex_date": date(2025, 9, 29),
            "amount": 2.4,
            "currency": "SEK",
            "dividend_type": 3,
            "status": "excluded",
            "reason": "wrong share class",
            "evidence_url": "https://example.com/evidence",
        }
    ]
    with patch(
        "kncompanyscraper.repositories.dividend_repository.get_connection",
        return_value=connection_with_cursor(cursor),
    ):
        result = DividendRepository().get_reviews(
            154,
            after_date=date(2025, 7, 31),
            through_date=date(2026, 7, 31),
            source="borsdata:dividend_calendar",
        )

    review = result[(date(2025, 9, 29), 2.4, "SEK", 3)]
    assert review.status == "excluded"
    assert review.reason == "wrong share class"


def test_review_events_upserts_matching_source_events():
    cursor = MagicMock(rowcount=4)
    with patch(
        "kncompanyscraper.repositories.dividend_repository.get_connection",
        return_value=connection_with_cursor(cursor),
    ):
        count = DividendRepository().review_events(
            154,
            after_date=date(2025, 7, 31),
            through_date=date(2026, 7, 31),
            status="excluded",
            reason=" wrong share class ",
            evidence_url="https://example.com/evidence",
            source="borsdata:dividend_calendar",
        )

    assert count == 4
    assert cursor.execute.call_args.args[1] == (
        "excluded",
        "wrong share class",
        "https://example.com/evidence",
        154,
        date(2025, 7, 31),
        date(2026, 7, 31),
        "borsdata:dividend_calendar",
    )


@pytest.mark.parametrize(
    ("status", "reason", "message"),
    [
        ("ignored", "reason", "unsupported"),
        ("pending", " ", "reason is required"),
    ],
)
def test_review_events_validates_decision(status, reason, message):
    with pytest.raises(ValueError, match=message):
        DividendRepository().review_events(
            1,
            after_date=date(2025, 1, 1),
            through_date=date(2025, 12, 31),
            status=status,
            reason=reason,
            evidence_url=None,
            source="borsdata:dividend_calendar",
        )

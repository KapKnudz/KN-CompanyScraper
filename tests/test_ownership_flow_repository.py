from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from kncompanyscraper.models.ownership_flow import (
    BuybackEvent,
    StoredBuybackEvent,
    StoredShortInterestSnapshot,
)
from kncompanyscraper.repositories.ownership_flow_repository import OwnershipFlowRepository


def test_buyback_upsert_preserves_raw_fields():
    cursor = MagicMock()
    cursor.rowcount = 1
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    event = BuybackEvent(
        date(2026, 8, 20), -1000, -0.25, 42.5, "SEK", 5000, 1.25,
        {"changeProc": -0.25},
    )

    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection,
    ):
        count = OwnershipFlowRepository().save_buybacks(7, (event,))

    sql, params = cursor.execute.call_args.args
    assert "ON CONFLICT" in sql
    assert params[:9] == (
        7, date(2026, 8, 20), -1000, -0.25, 42.5, "SEK", 5000, 1.25,
        "borsdata",
    )
    assert count == 1


def test_buyback_read_is_as_of_safe_and_returns_typed_rows():
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "company_id": 7,
            "event_date": date(2026, 8, 20),
            "change_shares": -1000,
            "change_pct_raw": Decimal("-0.25"),
            "reported_price": Decimal("42.5"),
            "currency": "SEK",
            "treasury_shares": 5000,
            "treasury_shares_pct_raw": Decimal("1.25"),
            "source": "borsdata",
            "raw_payload": {"changeProc": -0.25},
        }
    ]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection,
    ):
        rows = OwnershipFlowRepository().list_buybacks_as_of(
            7, date(2026, 8, 31)
        )

    assert rows == (
        StoredBuybackEvent(
            7, date(2026, 8, 20), -1000, -0.25, 42.5, "SEK", 5000,
            1.25, "borsdata", {"changeProc": -0.25},
        ),
    )
    assert isinstance(rows[0].change_pct_raw, float)
    sql, params = cursor.execute.call_args.args
    assert "event_date <= %s" in sql
    assert "ORDER BY event_date DESC" in sql
    assert params == (7, date(2026, 8, 31))


def test_short_read_uses_observation_date_not_last_transaction_date():
    row = {
        "company_id": 7,
        "observation_date": date(2026, 8, 30),
        "short_pct_raw": Decimal("-1.5"),
        "reported_holder_count": Decimal("2.0"),
        "average_short_pct_raw": None,
        "short_value_millions_raw": Decimal("12.0"),
        "average_short_value_millions_raw": None,
        "last_transaction_date": date(2026, 9, 1),
        "days_to_cover_sum": None,
        "days_to_cover_average": None,
        "trend_1w": Decimal("-0.1"),
        "trend_1m": Decimal("0.2"),
        "trend_3m": Decimal("0.3"),
        "trend_6m": Decimal("0.4"),
        "source": "borsdata",
        "raw_payload": {},
    }
    cursor = MagicMock()
    cursor.fetchone.return_value = row
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection,
    ):
        snapshot = OwnershipFlowRepository().get_latest_short_as_of(
            7, date(2026, 8, 31)
        )

    assert snapshot == StoredShortInterestSnapshot(
        **{
            **row,
            "short_pct_raw": -1.5,
            "reported_holder_count": 2.0,
            "short_value_millions_raw": 12.0,
            "trend_1w": -0.1,
            "trend_1m": 0.2,
            "trend_3m": 0.3,
            "trend_6m": 0.4,
        }
    )
    assert isinstance(snapshot.short_pct_raw, float)
    sql, params = cursor.execute.call_args.args
    assert "observation_date <= %s" in sql
    assert "ORDER BY observation_date DESC" in sql
    assert "last_transaction_date <=" not in sql
    assert params == (7, date(2026, 8, 31))


def test_latest_job_coverage_preserves_separate_domain_states():
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "status": "failed",
        "result": {"coverage": {"buybacks": "available", "shorts": "failed"}},
    }
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection,
    ):
        coverage = OwnershipFlowRepository().get_latest_sync_coverage(7)

    assert coverage == {
        "job_status": "failed",
        "buybacks": "available",
        "shorts": "failed",
    }


def test_operational_coverage_queries_each_domain_without_merging_states():
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "company_id": 7,
            "name": "Test AB",
            "ticker": "TEST",
            "holdings_coverage": {"buybacks": "empty", "shorts": "unknown"},
        }
    ]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection,
    ):
        rows = OwnershipFlowRepository().get_operational_coverage([7, 8])

    sql, params = cursor.execute.call_args.args
    assert "volume IS NOT NULL" in sql
    assert "company_buyback_events" in sql
    assert "company_short_snapshots" in sql
    assert "result->'coverage' AS holdings_coverage" in sql
    assert "c.id = ANY(%s)" in sql
    assert params == ([7, 8],)
    assert rows[0]["holdings_coverage"] == {
        "buybacks": "empty",
        "shorts": "unknown",
    }

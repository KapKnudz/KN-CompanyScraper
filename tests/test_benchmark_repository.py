from datetime import date
from unittest.mock import MagicMock, patch

from kncompanyscraper.repositories.benchmark_repository import BenchmarkRepository


def connection_with_cursor(cursor):
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn


def test_benchmark_lookup_enforces_max_distance():
    cursor = MagicMock()
    cursor.fetchone.return_value = [date(2026, 2, 10), 500.0]

    with patch(
        "kncompanyscraper.repositories.benchmark_repository.get_connection",
        return_value=connection_with_cursor(cursor),
    ):
        result = BenchmarkRepository().get_value_on_or_after(
            "OMXS30GI", date(2026, 2, 1), max_age_days=7
        )

    assert result is None


def test_benchmark_return_basis_is_read_from_series():
    cursor = MagicMock()
    cursor.fetchone.return_value = ["gross_total_return"]

    with patch(
        "kncompanyscraper.repositories.benchmark_repository.get_connection",
        return_value=connection_with_cursor(cursor),
    ):
        result = BenchmarkRepository().get_return_basis("OMXS30GI")

    assert result == "gross_total_return"


def test_benchmark_latest_date_is_read_from_series():
    cursor = MagicMock()
    cursor.fetchone.return_value = [date(2026, 8, 17)]

    with patch(
        "kncompanyscraper.repositories.benchmark_repository.get_connection",
        return_value=connection_with_cursor(cursor),
    ):
        result = BenchmarkRepository().get_latest_date("OMXS30GI")

    assert result == date(2026, 8, 17)
    assert cursor.execute.call_args.args[1] == ("OMXS30GI",)

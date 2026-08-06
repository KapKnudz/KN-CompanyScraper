from unittest.mock import MagicMock

import pytest

from kncompanyscraper.watchlist_import import (
    WatchlistCompany,
    WatchlistImportService,
)


def test_imports_utf8_bom_semicolon_csv(tmp_path):
    csv_path = tmp_path / "watchlist.csv"
    csv_path.write_text(
        "\ufeffId;Name;Ticker\n426;Gränges;GRNG\n2516;Navigo Invest;NAVIGO STAM\n",
        encoding="utf-8",
    )
    repository = MagicMock()
    repository.upsert_watchlist_companies.return_value = (2, 0)

    result = WatchlistImportService(repository).import_file(csv_path)

    assert result.imported == 2
    assert result.created == 2
    assert result.updated == 0
    repository.upsert_watchlist_companies.assert_called_once_with(
        [
            WatchlistCompany(426, "Gränges", "GRNG"),
            WatchlistCompany(2516, "Navigo Invest", "NAVIGO STAM"),
        ]
    )


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("borsdata_id;name;ticker\n1;Example;EX\n", "CSV header must be"),
        ("Id;Name;Ticker\nabc;Example;EX\n", "invalid Börsdata ID"),
        ("Id;Name;Ticker\n1;Example\n", "must contain exactly 3 columns"),
        ("Id;Name;Ticker\n1;Example;EX;extra\n", "must contain exactly 3 columns"),
        ("Id;Name;Ticker\n1;;EX\n", "empty required value"),
        ("Id;Name;Ticker\n1;One;ONE\n1;Two;TWO\n", "duplicates Börsdata ID"),
        ("Id;Name;Ticker\n1;One;SAME\n2;Two;same\n", "duplicates ticker"),
        (f"Id;Name;Ticker\n1;One;{'X' * 21}\n", "exceeds 20 characters"),
        ("Id;Name;Ticker\n", "contains no companies"),
    ],
)
def test_rejects_invalid_csv_before_database_write(tmp_path, contents, message):
    csv_path = tmp_path / "watchlist.csv"
    csv_path.write_text(contents, encoding="utf-8")
    repository = MagicMock()

    with pytest.raises(ValueError, match=message):
        WatchlistImportService(repository).import_file(csv_path)

    repository.upsert_watchlist_companies.assert_not_called()

from unittest.mock import MagicMock, patch

from kncompanyscraper.repositories.company_repository import CompanyRepository
from kncompanyscraper.watchlist_import import WatchlistCompany


def test_set_borsdata_identity_updates_id_and_listing_currency():
    cursor = MagicMock()
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.company_repository.get_connection",
        return_value=connection,
    ):
        CompanyRepository().set_borsdata_identity(7, 700, "SEK")

    sql, params = cursor.execute.call_args[0]
    assert "SET borsdata_id = %s" in sql
    assert params == (700, "SEK", 7)


def test_upsert_watchlist_companies_creates_and_activates_new_company():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [None, None, (42,)]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.company_repository.get_connection",
        return_value=connection,
    ):
        result = CompanyRepository().upsert_watchlist_companies(
            [WatchlistCompany(2516, "Navigo Invest", "NAVIGO STAM")]
        )

    assert result == (1, 0)
    queries = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("INSERT INTO companies" in query for query in queries)
    assert any("INSERT INTO watchlist" in query for query in queries)


def test_upsert_watchlist_companies_updates_existing_borsdata_company():
    cursor = MagicMock()
    cursor.fetchone.return_value = (7,)
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.company_repository.get_connection",
        return_value=connection,
    ):
        result = CompanyRepository().upsert_watchlist_companies(
            [WatchlistCompany(426, "Gränges", "GRNG")]
        )

    assert result == (0, 1)
    update_call = next(
        call for call in cursor.execute.call_args_list if "UPDATE companies" in call.args[0]
    )
    assert update_call.args[1] == ("Gränges", "GRNG", 426, 7)


def test_upsert_watchlist_companies_falls_back_to_existing_ticker():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [None, (9,)]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.company_repository.get_connection",
        return_value=connection,
    ):
        result = CompanyRepository().upsert_watchlist_companies(
            [WatchlistCompany(426, "Gränges", "GRNG")]
        )

    assert result == (0, 1)
    update_call = next(
        call for call in cursor.execute.call_args_list if "UPDATE companies" in call.args[0]
    )
    assert update_call.args[1] == ("Gränges", "GRNG", 426, 9)

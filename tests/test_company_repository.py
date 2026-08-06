from unittest.mock import MagicMock, patch

from kncompanyscraper.repositories.company_repository import CompanyRepository


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

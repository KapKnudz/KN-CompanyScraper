from unittest.mock import MagicMock, patch

import pytest

from kncompanyscraper.database import get_connection


def test_get_connection_commits_and_closes_on_success():
    connection = MagicMock()
    with patch("kncompanyscraper.database.psycopg2.connect", return_value=connection):
        with get_connection() as yielded:
            assert yielded is connection

    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    connection.close.assert_called_once_with()


def test_get_connection_rolls_back_and_closes_on_query_failure():
    connection = MagicMock()
    with patch("kncompanyscraper.database.psycopg2.connect", return_value=connection):
        with pytest.raises(RuntimeError, match="query failed"):
            with get_connection():
                raise RuntimeError("query failed")

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once_with()
    connection.close.assert_called_once_with()


def test_get_connection_does_not_mask_connect_failure():
    with patch(
        "kncompanyscraper.database.psycopg2.connect",
        side_effect=ConnectionError("database unavailable"),
    ):
        with pytest.raises(ConnectionError, match="database unavailable"):
            with get_connection():
                pass

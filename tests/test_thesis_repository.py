from datetime import date
from unittest.mock import MagicMock, patch

from kncompanyscraper.repositories.thesis_repository import ThesisRepository


def test_get_latest_thesis_returns_current_revision():
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "id": 8,
        "company_id": 42,
        "revision": 3,
        "evidence_as_of": date(2026, 8, 16),
        "content": {"verdict": "watch"},
    }
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection,
    ):
        thesis = ThesisRepository().get_latest(42)

    assert thesis["revision"] == 3
    assert thesis["content"]["verdict"] == "watch"
    assert cursor.execute.call_args.args[1] == (42,)


def test_get_revision_loads_an_exact_revision():
    cursor = MagicMock()
    cursor.fetchone.return_value = {"id": 9, "company_id": 42, "revision": 2}
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection,
    ):
        thesis = ThesisRepository().get_revision(9)

    assert thesis == {"id": 9, "company_id": 42, "revision": 2}
    assert cursor.execute.call_args.args[1] == (9,)


def test_list_latest_facts_scopes_query_to_latest_revision():
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "id": 1,
            "company_id": 42,
            "heading": "business_model",
            "statement": "The company sells subscriptions.",
        }
    ]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection,
    ):
        facts = ThesisRepository().list_latest_facts(42)

    assert facts[0]["heading"] == "business_model"
    assert cursor.execute.call_args.args[1] == (42, 42)

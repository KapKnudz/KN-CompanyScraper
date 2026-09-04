from unittest.mock import MagicMock

from kncompanyscraper.repositories.research_document_repository import (
    ResearchDocumentRepository,
)


def test_update_metadata_merges_fields_without_replacing_existing_metadata():
    cursor = MagicMock(rowcount=1)
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    updated = ResearchDocumentRepository(connection).update_metadata(
        42, {"report_year": 2025, "report_period": 4}
    )

    sql, params = cursor.execute.call_args.args
    assert "metadata = metadata || %s" in sql
    assert params[0].adapted == {"report_year": 2025, "report_period": 4}
    assert params[1] == 42
    assert updated is True

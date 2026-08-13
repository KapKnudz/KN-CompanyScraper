from unittest.mock import MagicMock, patch

from kncompanyscraper.repositories.portfolio_repository import PortfolioRepository


def test_save_run_persists_portfolio_json_and_returns_id():
    cursor = MagicMock()
    cursor.fetchone.return_value = (9,)
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    run = {
        "as_of": "2026-08-12",
        "target_size": 5,
        "status": "not_ready",
        "selected": [],
    }

    with patch(
        "kncompanyscraper.repositories.portfolio_repository.get_connection",
        return_value=connection,
    ):
        run_id = PortfolioRepository().save_run(run)

    assert run_id == 9
    _, params = cursor.execute.call_args[0]
    assert params[:3] == ("2026-08-12", 5, "not_ready")
    assert params[3].adapted == run

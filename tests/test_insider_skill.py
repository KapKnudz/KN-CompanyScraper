from datetime import date, timedelta
from unittest.mock import MagicMock

from kncompanyscraper.analysis.insider.insider_skill import InsiderSkill
from kncompanyscraper.models.insider_transaction import InsiderTransaction


def make_transaction(transaction_type: str, value: float, days_ago: int):
    return InsiderTransaction(
        person_name=f"{transaction_type}-{days_ago}",
        person_role=None,
        transaction_type=transaction_type,
        shares=10,
        price_per_share=value / 10,
        total_value=value,
        transaction_date=date.today() - timedelta(days=days_ago),
    )


def test_insider_skill_uses_recent_ninety_days_as_current_activity():
    repository = MagicMock()
    repository.list_for_company.return_value = [
        make_transaction("buy", 1000.0, 10),
        make_transaction("sell", 250.0, 20),
        make_transaction("buy", 100.0, 120),
    ]
    company = MagicMock(id=7)

    result = InsiderSkill(repository).run(company)

    assert result.net_buying == 750.0
    assert result.buy_sell_ratio == 4.0
    repository.list_for_company.assert_called_once_with(7)

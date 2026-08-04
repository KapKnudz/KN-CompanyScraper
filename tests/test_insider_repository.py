from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from kncompanyscraper.models.insider_transaction import InsiderTransaction
from kncompanyscraper.repositories.insider_repository import InsiderRepository


def make_transaction(**overrides) -> InsiderTransaction:
    defaults = dict(
        person_name="Andersson, Erik",
        person_role="CEO",
        transaction_type="buy",
        shares=15000,
        price_per_share=245.50,
        total_value=3682500.00,
        transaction_date=date(2026, 6, 15),
        source="finansinspektionen",
    )
    defaults.update(overrides)
    return InsiderTransaction(**defaults)


def _mock_connection(cursor: MagicMock) -> MagicMock:
    """Set up a MagicMock connection that returns the given cursor."""
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn


class TestInsiderRepository:

    # --- save ---

    def test_save_inserts_correct_row(self):
        """save() executes INSERT with all columns mapped from the dataclass."""
        mock_cur = MagicMock()
        mock_conn = _mock_connection(mock_cur)

        with patch(
            "kncompanyscraper.repositories.insider_repository.get_connection",
            return_value=mock_conn,
        ):
            repo = InsiderRepository()
            txn = make_transaction()
            repo.save(txn, company_id=42)

        mock_cur.execute.assert_called_once()
        sql, params = mock_cur.execute.call_args[0]
        assert "INSERT INTO insider_transactions" in sql
        assert params == (
            42,
            "Andersson, Erik",
            "CEO",
            "buy",
            15000,
            245.50,
            3682500.00,
            date(2026, 6, 15),
            "finansinspektionen",
        )

    def test_save_handles_nullable_fields(self):
        """Nullable fields (role, price, total_value, source) pass None cleanly."""
        mock_cur = MagicMock()
        mock_conn = _mock_connection(mock_cur)

        with patch(
            "kncompanyscraper.repositories.insider_repository.get_connection",
            return_value=mock_conn,
        ):
            repo = InsiderRepository()
            txn = make_transaction(
                person_role=None,
                price_per_share=None,
                total_value=None,
                source=None,
            )
            repo.save(txn, company_id=1)

        _, params = mock_cur.execute.call_args[0]
        assert params[2] is None  # person_role
        assert params[5] is None  # price_per_share
        assert params[6] is None  # total_value
        assert params[8] is None  # source

    # --- list_for_company ---

    def test_list_for_company_returns_transactions(self):
        """Rows from the DB are converted to InsiderTransaction instances."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            {
                "person_name": "Andersson, Erik",
                "person_role": "CEO",
                "transaction_type": "buy",
                "shares": 15000,
                "price_per_share": 245.50,
                "total_value": 3682500.00,
                "transaction_date": date(2026, 6, 15),
                "source": "fi",
            },
        ]
        mock_conn = _mock_connection(mock_cur)

        with patch(
            "kncompanyscraper.repositories.insider_repository.get_connection",
            return_value=mock_conn,
        ):
            repo = InsiderRepository()
            results = repo.list_for_company(company_id=42)

        assert len(results) == 1
        txn = results[0]
        assert txn.person_name == "Andersson, Erik"
        assert txn.transaction_type == "buy"
        assert txn.shares == 15000
        assert txn.price_per_share == 245.50
        assert txn.total_value == 3682500.00

    def test_list_for_company_orders_by_date_desc(self):
        """The SQL includes ORDER BY transaction_date DESC."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn = _mock_connection(mock_cur)

        with patch(
            "kncompanyscraper.repositories.insider_repository.get_connection",
            return_value=mock_conn,
        ):
            repo = InsiderRepository()
            repo.list_for_company(company_id=42)

        sql = mock_cur.execute.call_args[0][0]
        assert "ORDER BY transaction_date DESC" in sql

    def test_list_for_company_with_since_filter(self):
        """When `since` is given, the query includes a date filter."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn = _mock_connection(mock_cur)

        with patch(
            "kncompanyscraper.repositories.insider_repository.get_connection",
            return_value=mock_conn,
        ):
            repo = InsiderRepository()
            repo.list_for_company(company_id=42, since=date(2026, 1, 1))

        _, params = mock_cur.execute.call_args[0]
        assert params == (42, date(2026, 1, 1))

    def test_list_for_company_with_limit(self):
        """When `limit` is given, the query includes LIMIT clause."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn = _mock_connection(mock_cur)

        with patch(
            "kncompanyscraper.repositories.insider_repository.get_connection",
            return_value=mock_conn,
        ):
            repo = InsiderRepository()
            repo.list_for_company(company_id=42, limit=10)

        sql = mock_cur.execute.call_args[0][0]
        assert "LIMIT %s" in sql
        _, params = mock_cur.execute.call_args[0]
        assert params == (42, 10)

    def test_list_for_company_with_since_and_limit(self):
        """Both `since` and `limit` can be combined."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn = _mock_connection(mock_cur)

        with patch(
            "kncompanyscraper.repositories.insider_repository.get_connection",
            return_value=mock_conn,
        ):
            repo = InsiderRepository()
            repo.list_for_company(
                company_id=42, since=date(2026, 1, 1), limit=5
            )

        _, params = mock_cur.execute.call_args[0]
        assert params == (42, date(2026, 1, 1), 5)

    def test_list_for_company_empty_result(self):
        """No rows returns an empty list, not None."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn = _mock_connection(mock_cur)

        with patch(
            "kncompanyscraper.repositories.insider_repository.get_connection",
            return_value=mock_conn,
        ):
            repo = InsiderRepository()
            results = repo.list_for_company(company_id=99)

        assert results == []

    # --- get_recent_for_company ---

    def test_get_recent_defaults_to_20(self):
        """get_recent_for_company passes limit=20 to list_for_company by default."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn = _mock_connection(mock_cur)

        with patch(
            "kncompanyscraper.repositories.insider_repository.get_connection",
            return_value=mock_conn,
        ):
            repo = InsiderRepository()
            repo.get_recent_for_company(company_id=42)

        _, params = mock_cur.execute.call_args[0]
        assert params == (42, 20)

    def test_get_recent_custom_limit(self):
        """get_recent_for_company respects an explicit limit."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn = _mock_connection(mock_cur)

        with patch(
            "kncompanyscraper.repositories.insider_repository.get_connection",
            return_value=mock_conn,
        ):
            repo = InsiderRepository()
            repo.get_recent_for_company(company_id=42, limit=5)

        _, params = mock_cur.execute.call_args[0]
        assert params == (42, 5)

    # --- type edge cases ---

    def test_numeric_db_values_cast_to_float(self):
        """Psycopg2 returns Decimal for numeric columns; repository casts to float."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            {
                "person_name": "Test",
                "person_role": None,
                "transaction_type": "buy",
                "shares": 10,
                "price_per_share": Decimal("100.50"),
                "total_value": Decimal("1005.00"),
                "transaction_date": date(2026, 1, 1),
                "source": None,
            },
        ]
        mock_conn = _mock_connection(mock_cur)

        with patch(
            "kncompanyscraper.repositories.insider_repository.get_connection",
            return_value=mock_conn,
        ):
            repo = InsiderRepository()
            results = repo.list_for_company(company_id=1)

        txn = results[0]
        assert isinstance(txn.price_per_share, float)
        assert isinstance(txn.total_value, float)
        assert txn.price_per_share == 100.50
        assert txn.total_value == 1005.00

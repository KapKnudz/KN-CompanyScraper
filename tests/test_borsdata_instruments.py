from unittest.mock import MagicMock

from kncompanyscraper.borsdata.instrument import Instrument, match_instrument
from kncompanyscraper.borsdata.instrument_mapping import BorsdataInstrumentMappingService
from kncompanyscraper.models.company import Company


def make_company(ticker="TEST", isin=None, company_id=1):
    return Company(
        id=company_id,
        name="Test Company",
        ticker=ticker,
        mfn_slug=None,
        borsdata_id=None,
        last_updated=None,
        isin=isin,
    )


def test_match_instrument_prefers_exact_isin():
    company = make_company(ticker="DUP", isin="SE0000000001")
    instruments = [
        Instrument(10, "Wrong", "SE0000000002", "DUP"),
        Instrument(20, "Right", "se0000000001", "OTHER"),
    ]

    assert match_instrument(company, instruments).id == 20


def test_match_instrument_requires_unique_ticker():
    company = make_company(ticker="DUP")
    instruments = [
        Instrument(10, "First", None, "DUP"),
        Instrument(20, "Second", None, "dup"),
    ]

    assert match_instrument(company, instruments) is None


def test_match_instrument_does_not_fall_back_when_isin_is_present_but_wrong():
    company = make_company(ticker="TEST", isin="SE0000000099")
    instruments = [Instrument(10, "Ticker match", "SE0000000010", "TEST")]

    assert match_instrument(company, instruments) is None


def test_mapping_service_persists_only_resolved_companies():
    companies = [make_company(ticker="ONE", company_id=1), make_company(ticker="MISSING", company_id=2)]
    client = MagicMock()
    client.get_instruments.return_value = [Instrument(101, "One", None, "ONE", "SEK")]
    repository = MagicMock()

    result = BorsdataInstrumentMappingService(client, repository).map_companies(companies)

    repository.set_borsdata_identity.assert_called_once_with(1, 101, "SEK")
    assert result.mapped == 1
    assert result.unresolved == ["Test Company"]

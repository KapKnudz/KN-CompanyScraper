from kncompanyscraper.borsdata.kpi_ids import KpiIds


def test_valuation_kpi_ids_match_borsdata_metadata():
    assert {
        "DIVIDEND_YIELD": KpiIds.DIVIDEND_YIELD,
        "PE": KpiIds.PE,
        "PS": KpiIds.PS,
        "PB": KpiIds.PB,
        "EV_EBIT": KpiIds.EV_EBIT,
        "EV_EBITDA": KpiIds.EV_EBITDA,
        "PEG": KpiIds.PEG,
        "ENTERPRISE_VALUE": KpiIds.ENTERPRISE_VALUE,
        "MARKET_CAP": KpiIds.MARKET_CAP,
        "PFCF": KpiIds.PFCF,
    } == {
        "DIVIDEND_YIELD": 1,
        "PE": 2,
        "PS": 3,
        "PB": 4,
        "EV_EBIT": 10,
        "EV_EBITDA": 11,
        "PEG": 19,
        "ENTERPRISE_VALUE": 49,
        "MARKET_CAP": 50,
        "PFCF": 76,
    }

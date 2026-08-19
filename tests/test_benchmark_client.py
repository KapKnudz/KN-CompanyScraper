from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest

from kncompanyscraper.benchmark_client import (
    NASDAQ_OMXS30GI_EXPORT_URL,
    NasdaqBenchmarkClient,
    parse_nasdaq_history_workbook,
)


def workbook(rows, headers=("Trade Date", "Index Value")):
    shared = "".join(f"<si><t>{value}</t></si>" for value in headers)
    body = "".join(
        f'<row r="{index}"><c r="A{index}"><v>{serial}</v></c>'
        f'<c r="B{index}"><v>{close}</v></c></row>'
        for index, (serial, close) in enumerate(rows, 2)
    )
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"{shared}</sst>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c>'
            '<c r="B1" t="s"><v>1</v></c></row>'
            f"{body}</sheetData></worksheet>",
        )
    return output.getvalue()


def test_parser_reads_and_sorts_nasdaq_history_workbook():
    result = parse_nasdaq_history_workbook(
        workbook([(45659, "200.5"), (45658, "198.25")])
    )

    assert result.values == [
        (date(2025, 1, 1), 198.25),
        (date(2025, 1, 2), 200.5),
    ]
    assert result.omitted_zero_dates == ()


def test_parser_rejects_unexpected_columns():
    with pytest.raises(ValueError, match="unexpected.*columns"):
        parse_nasdaq_history_workbook(workbook([], headers=("Date", "Close")))


def test_client_requests_bounded_official_eod_export():
    calls = []

    class Response:
        content = workbook([(45659, "200.5")])

        def raise_for_status(self):
            pass

    def request(url, params, timeout):
        calls.append((url, params, timeout))
        return Response()

    result = NasdaqBenchmarkClient(request).get_omxs30gi(
        date(2025, 1, 1), date(2025, 1, 31)
    )

    assert result.values == [(date(2025, 1, 2), 200.5)]
    assert calls == [
        (
            NASDAQ_OMXS30GI_EXPORT_URL,
            {
                "startDate": "2025-01-01T00:00:00.000",
                "endDate": "2025-01-31T00:00:00.000",
                "timeOfDay": "EOD",
            },
            60,
        )
    ]


def test_client_rejects_reversed_date_range_without_requesting():
    def unexpected_request(*args, **kwargs):
        raise AssertionError("request must not run")

    with pytest.raises(ValueError, match="start date"):
        NasdaqBenchmarkClient(unexpected_request).get_omxs30gi(
            date(2025, 2, 1), date(2025, 1, 1)
        )


def test_parser_reports_and_omits_zero_values():
    result = parse_nasdaq_history_workbook(
        workbook([(45659, "200.5"), (45658, "0")])
    )

    assert result.values == [(date(2025, 1, 2), 200.5)]
    assert result.omitted_zero_dates == (date(2025, 1, 1),)

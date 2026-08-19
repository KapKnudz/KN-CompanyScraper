from dataclasses import dataclass
from datetime import date, timedelta
from io import BytesIO
from math import isfinite
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import requests


NASDAQ_OMXS30GI_EXPORT_URL = (
    "https://indexes.nasdaq.com/Index/ExportHistory/OMXS30GI"
)
NASDAQ_OMXS30GI_SOURCE = "Nasdaq Global Index Watch ExportHistory/OMXS30GI"
_XML_NAMESPACE = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_EXCEL_EPOCH = date(1899, 12, 30)


@dataclass(frozen=True)
class NasdaqBenchmarkHistory:
    values: list[tuple[date, float]]
    omitted_zero_dates: tuple[date, ...]


class NasdaqBenchmarkClient:
    def __init__(self, request_func=None):
        self.request_func = request_func or requests.get

    def get_omxs30gi(
        self, start_date: date, end_date: date
    ) -> NasdaqBenchmarkHistory:
        if start_date > end_date:
            raise ValueError("benchmark start date must not exceed end date")
        response = self.request_func(
            NASDAQ_OMXS30GI_EXPORT_URL,
            params={
                "startDate": f"{start_date.isoformat()}T00:00:00.000",
                "endDate": f"{end_date.isoformat()}T00:00:00.000",
                "timeOfDay": "EOD",
            },
            timeout=60,
        )
        response.raise_for_status()
        return parse_nasdaq_history_workbook(response.content)


def parse_nasdaq_history_workbook(content: bytes) -> NasdaqBenchmarkHistory:
    try:
        with ZipFile(BytesIO(content)) as workbook:
            shared_strings = _read_shared_strings(workbook)
            sheet = ElementTree.fromstring(
                workbook.read("xl/worksheets/sheet1.xml")
            )
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValueError("invalid Nasdaq history workbook") from exc

    rows = sheet.findall(".//x:sheetData/x:row", _XML_NAMESPACE)
    if not rows:
        raise ValueError("Nasdaq history workbook is empty")
    header = _row_values(rows[0], shared_strings)
    if header.get("A") != "Trade Date" or header.get("B") != "Index Value":
        raise ValueError("unexpected Nasdaq history workbook columns")

    values = []
    omitted_zero_dates = []
    seen_dates = set()
    for row in rows[1:]:
        cells = _row_values(row, shared_strings)
        if not cells:
            continue
        if "A" not in cells or "B" not in cells:
            raise ValueError("incomplete Nasdaq history workbook row")
        serial = float(cells["A"])
        if not serial.is_integer():
            raise ValueError("invalid Nasdaq trade date")
        price_date = _EXCEL_EPOCH + timedelta(days=int(serial))
        close = float(cells["B"])
        if not isfinite(close) or close < 0:
            raise ValueError(f"invalid Nasdaq index value on {price_date}")
        if price_date in seen_dates:
            raise ValueError(f"duplicate Nasdaq index date {price_date}")
        seen_dates.add(price_date)
        if close == 0:
            omitted_zero_dates.append(price_date)
            continue
        values.append((price_date, close))

    if not values:
        raise ValueError("Nasdaq history workbook contains no values")
    return NasdaqBenchmarkHistory(sorted(values), tuple(sorted(omitted_zero_dates)))


def _read_shared_strings(workbook: ZipFile) -> list[str]:
    root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
    return [
        "".join(text.text or "" for text in item.findall(".//x:t", _XML_NAMESPACE))
        for item in root.findall("x:si", _XML_NAMESPACE)
    ]


def _row_values(row, shared_strings: list[str]) -> dict[str, str]:
    values = {}
    for cell in row.findall("x:c", _XML_NAMESPACE):
        reference = cell.attrib.get("r", "")
        column = "".join(character for character in reference if character.isalpha())
        value = cell.find("x:v", _XML_NAMESPACE)
        if not column or value is None or value.text is None:
            continue
        text = value.text
        if cell.attrib.get("t") == "s":
            try:
                text = shared_strings[int(text)]
            except (IndexError, ValueError) as exc:
                raise ValueError("invalid Nasdaq shared string reference") from exc
        values[column] = text
    return values

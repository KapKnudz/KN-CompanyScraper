"""Shared domain constants used by ingestion and persisted analysis."""

BORSDATA_DIVIDEND_SOURCE = "borsdata:dividend_calendar"

REPORT_TITLE_TERMS = (
    "annual report",
    "interim report",
    "quarterly report",
    "year-end report",
    "årsredovisning",
    "delårsrapport",
    "kvartalsrapport",
    "bokslutskommuniké",
)

RAW_RESPONSE_TRANSIENT_METADATA_KEYS = (
    "analysis_mode",
    "validation_status",
    "validation_error",
)

from dataclasses import dataclass

from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_stock_analysis_result,
)
from kncompanyscraper.analysis.agent.output_schema import StockAnalysisResult


@dataclass(frozen=True)
class PersistedStockAnalysis:
    analysis_id: int
    result: StockAnalysisResult


class AgentExecutionBoundary:
    def __init__(self, analysis_repository):
        self.analysis_repository = analysis_repository

    def persist_response(
        self,
        raw_response: str,
        candidate,
        created_by: str,
        metadata: dict | None = None,
    ) -> PersistedStockAnalysis:
        result = parse_stock_analysis_result(raw_response)
        if result.company_id != candidate.company_id:
            raise StockAnalysisValidationError(
                f"result.company_id {result.company_id} does not match candidate {candidate.company_id}"
            )
        if result.ticker.strip().upper() != candidate.ticker.strip().upper():
            raise StockAnalysisValidationError(
                f"result.ticker {result.ticker!r} does not match candidate {candidate.ticker!r}"
            )

        analysis_id = self.analysis_repository.save_stock_analysis(
            result,
            created_by=created_by,
            metadata=metadata,
        )
        return PersistedStockAnalysis(analysis_id=analysis_id, result=result)

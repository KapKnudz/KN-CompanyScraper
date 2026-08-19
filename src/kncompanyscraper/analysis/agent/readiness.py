from dataclasses import dataclass
from math import isfinite
from typing import Literal


ReadinessStatus = Literal[
    "ready",
    "evidence_blocked",
    "valuation_blocked",
    "method_unsupported",
]
BlockerCategory = Literal["evidence", "valuation", "method"]


@dataclass(frozen=True)
class ReadinessBlocker:
    code: str
    category: BlockerCategory
    message: str


@dataclass(frozen=True)
class AgentReadinessAssessment:
    company_id: int
    ticker: str
    status: ReadinessStatus
    blockers: tuple[ReadinessBlocker, ...] = ()

    @property
    def ready(self) -> bool:
        return self.status == "ready"


class AgentReadinessError(ValueError):
    def __init__(self, assessments: tuple[AgentReadinessAssessment, ...]):
        self.assessments = assessments
        details = []
        for assessment in assessments:
            blockers = "; ".join(
                f"{blocker.code}: {blocker.message}"
                for blocker in assessment.blockers
            )
            details.append(f"{assessment.ticker} [{assessment.status}]: {blockers}")
        super().__init__("Agent analysis readiness check failed: " + " | ".join(details))


class AgentReadinessGate:
    """Reject known-incomplete analysis packets before a paid model call."""

    SUPPORTED_RANKING_MODELS = {"general"}

    def assess(self, candidate) -> AgentReadinessAssessment:
        blockers: list[ReadinessBlocker] = []
        if candidate.ranking_model not in self.SUPPORTED_RANKING_MODELS:
            blockers.append(
                ReadinessBlocker(
                    code="forward_method_unsupported",
                    category="method",
                    message=(
                        f"{candidate.ranking_model} requires a dedicated forward "
                        "valuation method"
                    ),
                )
            )

        if not candidate.research_evidence.get("documents"):
            blockers.append(
                ReadinessBlocker(
                    code="primary_evidence_missing",
                    category="evidence",
                    message="no textual company reports or releases are stored",
                )
            )

        reverse_dcf = candidate.full_results.get("reverse_dcf") or {}
        if _field(reverse_dcf, "status") != "available":
            blockers.extend(_reverse_dcf_blockers(reverse_dcf))

        valuation = candidate.full_results.get("valuation") or {}
        guardrail_low = _field(valuation, "ev_ebit_guardrail_low")
        guardrail_high = _field(valuation, "ev_ebit_guardrail_high")
        if (
            not _positive(guardrail_low)
            or not _positive(guardrail_high)
            or guardrail_low > guardrail_high
        ):
            blockers.append(
                ReadinessBlocker(
                    code="terminal_multiple_guardrail_unavailable",
                    category="valuation",
                    message="positive ordered EV/EBIT guardrails are unavailable",
                )
            )

        cyclicality = candidate.full_results.get("cyclicality_consensus") or {}
        if _field(cyclicality, "status") != "complete":
            blockers.append(
                ReadinessBlocker(
                    code="risk_profile_incomplete",
                    category="evidence",
                    message="completed cyclicality consensus is unavailable",
                )
            )

        return AgentReadinessAssessment(
            company_id=candidate.company_id,
            ticker=candidate.ticker,
            status=_status(blockers),
            blockers=tuple(blockers),
        )

    def require_ready(self, candidates: list) -> tuple[AgentReadinessAssessment, ...]:
        assessments = tuple(self.assess(candidate) for candidate in candidates)
        blocked = tuple(item for item in assessments if not item.ready)
        if blocked:
            raise AgentReadinessError(blocked)
        return assessments


def _status(blockers: list[ReadinessBlocker]) -> ReadinessStatus:
    categories = {blocker.category for blocker in blockers}
    if "method" in categories:
        return "method_unsupported"
    if "evidence" in categories:
        return "evidence_blocked"
    if "valuation" in categories:
        return "valuation_blocked"
    return "ready"


def _field(value, name):
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def _positive(value) -> bool:
    return isinstance(value, (int, float)) and isfinite(value) and value > 0


def _reverse_dcf_blockers(reverse_dcf) -> list[ReadinessBlocker]:
    missing = tuple(
        str(item)
        for item in (_field(reverse_dcf, "missing_information") or ())
    )
    matched = []
    checks = (
        (
            "stock price is older than",
            "stock_price_stale",
            "stored stock price is too old for the analysis date",
        ),
        (
            "latest stock price unavailable",
            "stock_price_missing",
            "latest stock price is unavailable",
        ),
        (
            "stock price and report currencies differ",
            "valuation_currency_mismatch",
            "stock-price and financial-report currencies differ",
        ),
    )
    for phrase, code, message in checks:
        if any(phrase in item for item in missing):
            matched.append(ReadinessBlocker(code, "valuation", message))
    if matched:
        return matched
    detail = "; ".join(missing) or "reverse DCF is unavailable"
    return [ReadinessBlocker("reverse_dcf_unavailable", "valuation", detail)]

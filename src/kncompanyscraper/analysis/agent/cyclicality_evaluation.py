from dataclasses import asdict, dataclass
import json
import re

from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt


DIMENSION_NAMES = (
    "revenue_recurrence",
    "economic_demand_sensitivity",
    "customer_concentration",
    "project_dependence",
    "order_phasing",
    "commodity_or_financing_exposure",
)
RECURRENCE_ASSESSMENTS = {
    "none_or_limited",
    "meaningful",
    "predominant",
    "unclassified",
}
CURVE_RISK_ASSESSMENTS = {"material", "unclassified"}
ORDER_PHASING_ASSESSMENTS = {"meaningful", "unclassified"}
CURVE_RISK_DIMENSIONS = (
    "economic_demand_sensitivity",
    "customer_concentration",
    "project_dependence",
    "commodity_or_financing_exposure",
)
CONSENSUS_POLICY_VERSION = "1.0.0"
CLASSIFIER_POLICY_VERSION = "2.1.0"
PASSAGE_TERMS = {
    "revenue_recurrence": (
        "recurr", "subscription", "saas", "renewal", "repeat revenue",
        "återkommande", "prenumeration", "förnyelse",
    ),
    "economic_demand_sensitivity": (
        "demand", "consumer", "economic", "recession", "cycle", "cyclical",
        "demand sensitivity", "efterfrågan", "konsument", "ekonomi", "konjunktur",
    ),
    "customer_concentration": (
        "customer concentration", "largest customer", "major customer", "customer mix",
        "customer base", "customer club", "loyalty club", "kundkoncentration",
        "största kund", "enskild kund", "kundmix", "kundbas", "kundklubb",
    ),
    "project_dependence": (
        "project", "contract", "backlog", "order book", "tender",
        "projekt", "entreprenad", "avtal", "orderstock", "upphandling",
    ),
    "order_phasing": (
        "order timing", "order phasing", "quarterly variation", "order variability",
        "timing of orders", "project payment", "tidpunkt", "ordervariation",
        "kvartalsvariation", "projektbetalning", "fluktuerar",
    ),
    "commodity_or_financing_exposure": (
        "commodity", "raw material", "material cost", "financing", "interest rate",
        "freight cost", "råvara", "materialkostnad", "finansiering", "ränta", "fraktkostnad",
    ),
}
class CyclicalityEvaluationError(ValueError):
    pass


@dataclass(frozen=True)
class CyclicalityCitation:
    passage_id: str
    source_id: str
    quote: str


@dataclass(frozen=True)
class CyclicalityDimension:
    assessment: str
    rationale: str
    passage_ids: list[str]


@dataclass(frozen=True)
class CyclicalityClassification:
    risk_profile: str
    confidence: str
    rationale: str
    evidence: list[CyclicalityCitation]
    missing_information: list[str]
    profile_driver: str
    dimensions: dict[str, CyclicalityDimension]
    warnings: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CyclicalityRun:
    company_id: int
    ticker: str
    company_name: str
    run: int
    response_id: str
    model: str
    usage: dict
    raw_response: str
    classification: CyclicalityClassification | None
    error: str | None

    def to_dict(self) -> dict:
        return asdict(self)


class CyclicalityPromptBuilder:
    def build(self, candidate, withhold_evidence: bool = False) -> AgentPrompt:
        documents = [] if withhold_evidence else candidate.research_evidence.get("documents", [])
        evidence = build_evidence_passages(documents)
        payload = {
            "company_id": candidate.company_id,
            "ticker": candidate.ticker,
            "company_name": candidate.name,
            "passages": evidence,
        }
        return AgentPrompt(
            system=(
                "Assess six business-risk dimensions using only the supplied passages. "
                "Do not produce a final risk profile; deterministic code owns that decision. "
                "For revenue_recurrence use only none_or_limited, meaningful, predominant, "
                "or unclassified; these describe the amount of recurring revenue, not risk. "
                "For economic_demand_sensitivity, customer_concentration, "
                "project_dependence, and commodity_or_financing_exposure use only material "
                "or unclassified. Material means the passages directly state or concretely "
                "demonstrate an exposure important enough to justify moving above the "
                "baseline valuation curve. Use material only when the passages show realized "
                "significant revenue, profit, or cash-flow damage; explicitly describe a "
                "significant or material exposure; or, for project dependence, establish a "
                "project-based business and large projects relative to its operations. "
                "Postponed decisions or longer sales cycles alone, generic risk-factor "
                "possibilities, ordinary business exposure, one contract or award without "
                "company scale, and absence of contrary evidence are insufficient. "
                "Project_dependence measures reliance on material projects or contracts. "
                "For order_phasing use meaningful or unclassified. It measures timing "
                "fluctuations only and never determines the risk profile. Recurring revenue "
                "does not prove economic resilience, and order timing does not prove "
                "economic cyclicality. "
                "For every assessment other than unclassified, cite one or more exact "
                "passage_ids. Absence of evidence means unclassified. Return JSON only."
            ),
            user=(
                json.dumps(payload, ensure_ascii=False, indent=2)
                + "\n\nReturn exactly these fields: dimensions, rationale, and "
                "missing_information. dimensions must contain exactly revenue_recurrence, "
                "economic_demand_sensitivity, customer_concentration, "
                "project_dependence, order_phasing, and commodity_or_financing_exposure. "
                "Each dimension must contain assessment, rationale, and passage_ids. "
                "missing_information must be an array of strings."
            ),
            policy_name="cyclicality-evaluation",
            policy_version=CLASSIFIER_POLICY_VERSION,
        )


class CyclicalityEvaluator:
    def __init__(self, model_adapter, prompt_builder=None):
        self.model_adapter = model_adapter
        self.prompt_builder = prompt_builder or CyclicalityPromptBuilder()

    def evaluate(self, candidates: list, runs: int) -> list[CyclicalityRun]:
        if runs < 2:
            raise ValueError("cyclicality evaluation requires at least two runs")

        results = []
        for candidate in candidates:
            documents = candidate.research_evidence.get("documents", [])
            for run in range(1, runs + 1):
                try:
                    response = self.model_adapter.generate(self.prompt_builder.build(candidate))
                except RuntimeError as exc:
                    results.append(self._failed_run(candidate, run, exc))
                    continue
                classification, error = _parse_run(response.output_text, documents)
                results.append(
                    CyclicalityRun(
                        company_id=candidate.company_id,
                        ticker=candidate.ticker,
                        company_name=candidate.name,
                        run=run,
                        response_id=response.response_id,
                        model=response.model,
                        usage=response.usage,
                        raw_response=response.output_text,
                        classification=classification,
                        error=error,
                    )
                )
        return results

    def negative_controls(self, candidates: list) -> list[CyclicalityRun]:
        results = []
        for candidate in candidates:
            try:
                response = self.model_adapter.generate(
                    self.prompt_builder.build(candidate, withhold_evidence=True)
                )
            except RuntimeError as exc:
                results.append(self._failed_run(candidate, 0, exc))
                continue
            classification, error = _parse_run(response.output_text, [])
            results.append(
                CyclicalityRun(
                    company_id=candidate.company_id,
                    ticker=candidate.ticker,
                    company_name=candidate.name,
                    run=0,
                    response_id=response.response_id,
                    model=response.model,
                    usage=response.usage,
                    raw_response=response.output_text,
                    classification=classification,
                    error=error,
                )
            )
        return results

    def _failed_run(self, candidate, run: int, error: RuntimeError) -> CyclicalityRun:
        return CyclicalityRun(
            company_id=candidate.company_id,
            ticker=candidate.ticker,
            company_name=candidate.name,
            run=run,
            response_id="",
            model=str(getattr(self.model_adapter, "model", "unknown")),
            usage={},
            raw_response="",
            classification=None,
            error=f"generation failed: {error}",
        )


def parse_cyclicality_classification(raw_response: str, documents: list[dict]):
    try:
        payload = json.loads(raw_response)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CyclicalityEvaluationError("response is not valid JSON") from exc

    payload, warnings = _normalize_payload(payload)

    if not isinstance(payload["dimensions"], dict) or set(payload["dimensions"]) != set(DIMENSION_NAMES):
        raise CyclicalityEvaluationError("dimensions do not match the evaluation contract")

    passages = {
        passage["passage_id"]: passage for passage in build_evidence_passages(documents)
    }
    dimensions = {}
    cited_passage_ids = []
    for name in DIMENSION_NAMES:
        item = payload["dimensions"][name]
        if not isinstance(item, dict) or set(item) != {
            "assessment",
            "rationale",
            "passage_ids",
        }:
            raise CyclicalityEvaluationError(f"invalid dimension: {name}")
        assessment = item["assessment"]
        passage_ids = item["passage_ids"]
        if name == "revenue_recurrence":
            allowed_assessments = RECURRENCE_ASSESSMENTS
        elif name == "order_phasing":
            allowed_assessments = ORDER_PHASING_ASSESSMENTS
        else:
            allowed_assessments = CURVE_RISK_ASSESSMENTS
        if assessment not in allowed_assessments:
            raise CyclicalityEvaluationError(f"unknown assessment for {name}")
        rationale = item["rationale"]
        if not isinstance(rationale, str):
            raise CyclicalityEvaluationError(f"rationale must be a string for {name}")
        if not rationale.strip():
            if assessment != "unclassified":
                raise CyclicalityEvaluationError(f"rationale must be non-empty for {name}")
            rationale = "No direct supporting evidence was supplied."
            warnings.append(f"empty unclassified rationale normalized: {name}")
        if not isinstance(passage_ids, list) or not all(
            isinstance(passage_id, str) for passage_id in passage_ids
        ):
            raise CyclicalityEvaluationError(f"passage_ids must contain strings for {name}")
        unknown = sorted(set(passage_ids) - set(passages))
        if unknown:
            raise CyclicalityEvaluationError(
                f"unknown passage for {name}: {', '.join(unknown)}"
            )
        if assessment == "unclassified" and passage_ids:
            raise CyclicalityEvaluationError(
                f"unclassified dimension cannot cite passages: {name}"
            )
        if assessment != "unclassified" and not passage_ids:
            raise CyclicalityEvaluationError(
                f"classified dimension requires passage evidence: {name}"
            )
        dimensions[name] = CyclicalityDimension(
            assessment=assessment,
            rationale=rationale,
            passage_ids=passage_ids,
        )
        cited_passage_ids.extend(passage_ids)

    risk_profile, profile_driver = derive_risk_profile(dimensions)
    unique_passage_ids = list(dict.fromkeys(cited_passage_ids))
    citations = [
        CyclicalityCitation(
            passage_id=passage_id,
            source_id=passages[passage_id]["source_id"],
            quote=passages[passage_id]["text"],
        )
        for passage_id in unique_passage_ids
    ]
    confidence = derive_confidence(risk_profile, dimensions, citations)

    return CyclicalityClassification(
        risk_profile=risk_profile,
        confidence=confidence,
        rationale=payload["rationale"],
        evidence=citations,
        missing_information=payload["missing_information"],
        profile_driver=profile_driver,
        dimensions=dimensions,
        warnings=warnings,
    )


def _normalize_payload(payload) -> tuple[dict, list[str]]:
    if not isinstance(payload, dict):
        raise CyclicalityEvaluationError("response must be a JSON object")
    warnings = []
    allowed = {"dimensions", "rationale", "missing_information"}
    ignored_identity = {"company_id", "ticker", "company_name"}
    unexpected = set(payload) - allowed - ignored_identity
    if unexpected:
        raise CyclicalityEvaluationError(
            "unexpected response fields: " + ", ".join(sorted(unexpected))
        )
    for field in sorted(set(payload).intersection(ignored_identity)):
        warnings.append(f"ignored echoed identity field: {field}")
    if "dimensions" not in payload:
        raise CyclicalityEvaluationError("response is missing dimensions")

    rationale = payload.get("rationale")
    if rationale is None or not isinstance(rationale, str) or not rationale.strip():
        rationale = "Dimension assessments derived from the supplied passages."
        warnings.append("missing or empty top-level rationale normalized")

    missing = payload.get("missing_information", [])
    if isinstance(missing, str):
        missing = [missing] if missing.strip() else []
        warnings.append("missing_information string normalized to array")
    if not isinstance(missing, list) or not all(isinstance(item, str) for item in missing):
        raise CyclicalityEvaluationError("missing_information must contain strings")
    if "missing_information" not in payload:
        warnings.append("missing missing_information normalized to empty array")

    return {
        "dimensions": payload["dimensions"],
        "rationale": rationale,
        "missing_information": missing,
    }, warnings


def build_evidence_passages(documents: list[dict], max_passages: int = 48) -> list[dict]:
    candidates = []
    for document in documents:
        source_id = document.get("source_id")
        if not source_id:
            continue
        paragraphs = [
            _compact(paragraph)
            for paragraph in re.split(r"\n\s*\n|(?<=\.)\s+(?=[A-ZÅÄÖ])", document.get("text", ""))
            if len(_compact(paragraph)) >= 40
        ]
        for index, paragraph in enumerate(paragraphs, 1):
            relevant_dimensions = _passage_dimensions(paragraph)
            if not relevant_dimensions:
                continue
            candidates.append(
                {
                    "passage_id": f"{source_id}#p{index}",
                    "source_id": source_id,
                    "title": document.get("title", ""),
                    "published_at": document.get("published_at"),
                    "relevant_dimensions": relevant_dimensions,
                    "text": paragraph[:1500],
                }
            )

    by_dimension = {
        name: [
            passage for passage in candidates if name in passage["relevant_dimensions"]
        ]
        for name in DIMENSION_NAMES
    }
    selected = {}
    offsets = {name: 0 for name in DIMENSION_NAMES}
    while len(selected) < max_passages:
        added = False
        for name in DIMENSION_NAMES:
            dimension_passages = by_dimension[name]
            while offsets[name] < len(dimension_passages):
                passage = dimension_passages[offsets[name]]
                offsets[name] += 1
                if passage["passage_id"] in selected:
                    continue
                selected[passage["passage_id"]] = passage
                added = True
                break
            if len(selected) >= max_passages:
                break
        if not added:
            break
    return list(selected.values())


def _passage_dimensions(paragraph: str) -> list[str]:
    normalized = paragraph.casefold()
    return [
        name
        for name, terms in PASSAGE_TERMS.items()
        if any(term in normalized for term in terms)
    ]


def derive_risk_profile(dimensions: dict[str, CyclicalityDimension]) -> tuple[str, str]:
    for name in CURVE_RISK_DIMENSIONS:
        if dimensions[name].assessment == "material":
            return "cyclical_or_other_risk", name
    return "slightly_cyclical", "baseline_no_material_risk"


def derive_confidence(
    risk_profile: str,
    dimensions: dict[str, CyclicalityDimension],
    citations: list[CyclicalityCitation],
) -> str:
    if risk_profile == "slightly_cyclical":
        return "low"
    source_count = len({citation.source_id for citation in citations})
    classified_dimensions = sum(
        dimensions[name].assessment != "unclassified"
        for name in ("revenue_recurrence", *CURVE_RISK_DIMENSIONS)
    )
    if source_count >= 2 and classified_dimensions >= 3:
        return "high"
    return "medium"


def build_cyclicality_consensus(
    runs: list[CyclicalityRun], required_runs: int = 3
) -> list[dict]:
    by_company = {}
    for run in runs:
        by_company.setdefault(run.ticker, []).append(run)

    results = []
    for ticker, company_runs in by_company.items():
        valid_runs = [run for run in company_runs if run.classification is not None]
        base = {
            "company_id": company_runs[0].company_id,
            "ticker": ticker,
            "company_name": company_runs[0].company_name,
            "required_run_count": required_runs,
            "valid_run_count": len(valid_runs),
        }
        if len(valid_runs) != required_runs:
            results.append(
                {
                    **base,
                    "status": "incomplete",
                    "risk_profile": None,
                    "profile_driver": None,
                    "consensus_strength": "incomplete",
                    "review_required": True,
                    "material_votes": {},
                    "material_runs": {},
                    "supporting_runs": [],
                    "evidence": [],
                }
            )
            continue

        material_votes = {
            name: sum(
                run.classification.dimensions[name].assessment == "material"
                for run in valid_runs
            )
            for name in CURVE_RISK_DIMENSIONS
        }
        material_runs = {
            name: [
                run.run
                for run in valid_runs
                if run.classification.dimensions[name].assessment == "material"
            ]
            for name in CURVE_RISK_DIMENSIONS
        }
        driver = max(CURVE_RISK_DIMENSIONS, key=material_votes.get)
        driver_votes = material_votes[driver]
        majority = required_runs // 2 + 1
        if driver_votes >= majority:
            risk_profile = "cyclical_or_other_risk"
            profile_driver = driver
            supporting = [
                run
                for run in valid_runs
                if run.classification.dimensions[driver].assessment == "material"
            ]
            supporting_runs = [run.run for run in supporting]
            passage_ids = {
                passage_id
                for run in supporting
                for passage_id in run.classification.dimensions[driver].passage_ids
            }
            evidence = []
            seen = set()
            for run in supporting:
                for citation in run.classification.evidence:
                    if citation.passage_id in passage_ids and citation.passage_id not in seen:
                        evidence.append(asdict(citation))
                        seen.add(citation.passage_id)
        else:
            risk_profile = "slightly_cyclical"
            profile_driver = "baseline_no_consensus_material_risk"
            supporting_runs = []
            evidence = []

        unanimous = driver_votes in (0, required_runs)
        results.append(
            {
                **base,
                "status": "complete",
                "risk_profile": risk_profile,
                "profile_driver": profile_driver,
                "consensus_strength": "unanimous" if unanimous else "majority",
                "review_required": not unanimous,
                "material_votes": material_votes,
                "material_runs": material_runs,
                "supporting_runs": supporting_runs,
                "evidence": evidence,
            }
        )
    return results


def cyclicality_run_from_dict(payload: dict) -> CyclicalityRun:
    classification_payload = payload.get("classification")
    classification = None
    if classification_payload is not None:
        classification = CyclicalityClassification(
            risk_profile=classification_payload["risk_profile"],
            confidence=classification_payload["confidence"],
            rationale=classification_payload["rationale"],
            evidence=[
                CyclicalityCitation(**citation)
                for citation in classification_payload.get("evidence", [])
            ],
            missing_information=classification_payload.get("missing_information", []),
            profile_driver=classification_payload["profile_driver"],
            dimensions={
                name: CyclicalityDimension(**dimension)
                for name, dimension in classification_payload["dimensions"].items()
            },
            warnings=classification_payload.get("warnings", []),
        )
    return CyclicalityRun(
        company_id=payload["company_id"],
        ticker=payload["ticker"],
        company_name=payload["company_name"],
        run=payload["run"],
        response_id=payload.get("response_id", ""),
        model=payload.get("model", "unknown"),
        usage=payload.get("usage", {}),
        raw_response=payload.get("raw_response", ""),
        classification=classification,
        error=payload.get("error"),
    )


def summarize_cyclicality_runs(runs: list[CyclicalityRun]) -> dict:
    by_company = {}
    for result in runs:
        by_company.setdefault(result.ticker, []).append(result)

    companies = []
    agreeing_pairs = 0
    total_pairs = 0
    for ticker, company_runs in by_company.items():
        profiles = [
            run.classification.risk_profile
            for run in company_runs
            if run.classification is not None
        ]
        pair_count = len(profiles) * (len(profiles) - 1) // 2
        matching = sum(
            profiles[left] == profiles[right]
            for left in range(len(profiles))
            for right in range(left + 1, len(profiles))
        )
        agreeing_pairs += matching
        total_pairs += pair_count
        companies.append(
            {
                "ticker": ticker,
                "company_name": company_runs[0].company_name,
                "profiles": profiles,
                "invalid_runs": sum(run.error is not None for run in company_runs),
                "warning_count": sum(
                    len(run.classification.warnings)
                    for run in company_runs
                    if run.classification is not None
                ),
                "unanimous": len(profiles) == len(company_runs) and len(set(profiles)) == 1,
                "pairwise_agreement": matching / pair_count if pair_count else None,
            }
        )

    return {
        "run_count": len(runs),
        "company_count": len(companies),
        "comparable_company_count": sum(
            len(company["profiles"]) >= 2 for company in companies
        ),
        "validation_pass_rate": (
            sum(run.error is None for run in runs) / len(runs) if runs else None
        ),
        "material_escalation_count": sum(
            run.classification is not None
            and run.classification.risk_profile == "cyclical_or_other_risk"
            for run in runs
        ),
        "normalization_warning_count": sum(
            len(run.classification.warnings)
            for run in runs
            if run.classification is not None
        ),
        "unanimous_company_rate": (
            sum(company["unanimous"] for company in companies) / len(companies)
            if companies
            else None
        ),
        "pairwise_profile_agreement": (
            agreeing_pairs / total_pairs if total_pairs else None
        ),
        "companies": companies,
    }


def _compact(value: str) -> str:
    return " ".join(value.split())


def _parse_run(raw_response: str, documents: list[dict]):
    try:
        return parse_cyclicality_classification(raw_response, documents), None
    except CyclicalityEvaluationError as exc:
        return None, str(exc)

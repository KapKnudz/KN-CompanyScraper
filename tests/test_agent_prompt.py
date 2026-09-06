import hashlib
import json
from datetime import date

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.agent_packet import (
    AgentCandidatePacket,
    build_source_aliases,
    deserialize_packet,
    resolve_source_id,
    serialize_packet,
)
from kncompanyscraper.analysis.agent.codex_exec import CodexExecAdapter
from kncompanyscraper.analysis.agent.context_provenance import deterministic_context_sha256
from kncompanyscraper.analysis.agent.output_schema import (
    EvidenceCitation,
    ManagementClaimAssessment,
    StockAnalysisResult,
)
from kncompanyscraper.analysis.agent.prompt_builder import AgentPromptBuilder
from kncompanyscraper.analysis.agent.packet_measurement import measure_text
from kncompanyscraper.analysis.financial.financial_result import FinancialResult
from kncompanyscraper.analysis.valuation.reverse_dcf_skill import ReverseDcfAnalysis


def test_prompt_builder_packages_policy_workflow_and_candidate_evidence():
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        total_score=81.5,
        full_results={
            "financial": FinancialResult(
                operating_margin=0.08,
                net_margin=0.05,
                fcf_margin=0.04,
                revenue_growth=0.18,
                ebit_growth=0.25,
                net_income_growth=0.20,
                roe=0.12,
                roa=0.07,
                debt_to_equity=0.30,
            ),
            "reverse_dcf": ReverseDcfAnalysis(
                status="unavailable",
                policy_version="reverse-dcf-v1",
                model="fcff",
                missing_information=("latest stock price unavailable",),
            ),
        },
        research_evidence={
            "as_of": "2026-08-09",
            "documents": [
                {
                    "source_id": "news:21",
                    "title": "Interim report Q2 2026",
                    "text": "Management expects continued growth.",
                }
            ],
        },
    )

    prompt = AgentPromptBuilder().build(candidate)

    assert "Three return engines" in prompt.system
    assert "Follow the steps in order" in prompt.system
    assert prompt.policy_name == "nordic-case-investing-policy"
    assert prompt.policy_version == "1.29.0-ownership-source-contract"
    assert prompt.contract_version == "qualitative-stage-prompt-v4-ownership-source-contract"
    assert "capital-allocation fact codes" in prompt.user
    assert "Never turn reverse-DCF curve labels" in prompt.user
    assert "structured_conclusions.missing_information_details" in prompt.user
    assert "half_year_comparison" in prompt.user
    assert "do not reconstruct H1" in prompt.user
    assert "individual-thesis-card-v3-structured-conclusions" in prompt.user
    assert '"structured_conclusions"' in prompt.user
    assert "analysis_status" in prompt.user
    assert "Deterministic valuation limitations may still be present" in prompt.user
    assert "Do not use `watch` merely as a synonym" in prompt.user
    assert "typed timing facts" in prompt.user
    assert prompt.policy_sha256 == hashlib.sha256(
        (
            AgentPromptBuilder._read_resource("resources/analyst_policy.md")
            + "\n\n"
            + AgentPromptBuilder._read_resource("resources/analysis_workflow.md")
        ).encode("utf-8")
    ).hexdigest()
    assert f"- Name: `{prompt.policy_name}`" in prompt.system
    assert f"- Version: `{prompt.policy_version}`" in prompt.system
    assert f"- SHA-256: `{prompt.policy_sha256}`" in prompt.system
    assert "full_results.reverse_dcf.implied_expectations" in prompt.system
    assert "Do not independently calculate or state a forward fair value" in prompt.system
    assert "alternative growth–margin combinations" in prompt.system
    assert "price_fundamental_attribution" in prompt.system
    assert "year-one revenue growth" in prompt.system
    assert "year-five EBIT margin" in prompt.system
    assert "Reverse DCF produces no scalar score" in prompt.system
    assert "revenue_resilience" in prompt.system
    assert "contractual or subscription stickiness" in prompt.system
    assert "market-cap bucket" in prompt.system
    assert "full-horizon decimal-fraction share-count growth" in prompt.system
    assert "deterministic engine derives diluted shares" in prompt.system
    assert "Do not invent a numeric confirmation threshold" in prompt.system
    assert "Do not invent a numerical return decomposition" in prompt.system
    assert "current price and market-implied operating expectation" in prompt.system
    assert "the valuation assumption" not in prompt.system
    assert "does not mean the company requires no reinvestment" in prompt.system
    assert "plausible`, `demanding`, `unsupported`, or `unassessable`" in prompt.system
    assert "Never apply a universal growth or margin cutoff" in prompt.system
    assert "never scores, probabilities, or generic valuation grades" in prompt.system
    assert "normalize a resolvable path" in prompt.system
    assert "Never invent or abbreviate a path" in prompt.system
    assert "A company buyback is capital allocation" in prompt.system
    assert '"company_id":42' in prompt.user
    assert '"operating_margin":0.08' in prompt.user
    assert '"policy_version":"reverse-dcf-v1"' in prompt.user
    assert '"latest stock price unavailable"' in prompt.user
    assert '"source_id":"news:21"' in prompt.user
    assert '"verdict": "reject | watch | latent_case | activated_case"' in prompt.user
    assert '"revenue_resilience"' in prompt.user
    assert prompt.packet_measurement["byte_count"] > 0
    assert prompt.packet_measurement["character_count"] > 0


def test_qualitative_prompt_marks_empty_unsourced_buyback_evidence_as_uncitable():
    candidate = _packet_candidate(1)
    candidate.research_evidence["ownership_liquidity"] = {
        "flow_signals": {
            "buybacks": {"status": "empty", "source_ids": []},
        },
        "source_ids": [],
    }

    prompt = AgentPromptBuilder().build(candidate)

    assert 'whose `status` is `empty` or `unknown`' in prompt.user
    assert "It is not citable evidence" in prompt.user
    assert '"buybacks":{"source_ids":[],"status":"empty"}' in prompt.user
    assert prompt.packet_measurement["document_count"] == 1
    assert prompt.packet_measurement["section_sizes"]["research_evidence"] > 0


def test_prompt_builder_serializes_dates_in_sector_kpi_history():
    candidate = AgentCandidate(
        rank=1,
        company_id=12,
        ticker="HUFV A",
        name="Hufvudstaden A",
        full_results={
            "sector_kpis": {
                "histories": {"property_value": [(date(2025, 12, 31), 52_000.0)]}
            }
        },
    )

    prompt = AgentPromptBuilder().build(candidate)

    assert '"2025-12-31"' in prompt.user
    assert len(deterministic_context_sha256(candidate)) == 64
    assert '"reverse_dcf_expectation_assessment"' in prompt.user
    assert '"portfolio_eligibility": "investable | not_investable"' in prompt.user
    assert "`activated_case` may be `investable`" in prompt.system


def test_agent_packet_catalog_accepts_integer_keyed_deterministic_maps():
    candidate = AgentCandidate(
        rank=1,
        company_id=12,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "peer_comparison": {
                12: {"source_ids": ["financial:12:2025:annual"]},
            }
        },
    )

    packet = AgentCandidatePacket.from_candidate(candidate)

    assert packet.evidence_catalog["financial_source_ids"] == [
        "financial:12:2025:annual"
    ]


def test_m1_msab_shape_uses_compact_catalog_without_leaf_alias_expansion(
    msab_catalog_shape,
):
    aliases = build_source_aliases(msab_catalog_shape, {})

    assert len(aliases) == 3
    assert "full_results.financial_history.annual.2024.revenue" not in aliases
    assert "full_results.peer_comparison.114.metrics.3" not in aliases
    assert aliases["full_results.peer_comparison"] == (
        "deterministic:peer_comparison"
    )


def test_m1_full_input_contains_one_compact_catalog(
    msab_catalog_shape,
):
    candidate = AgentCandidate(
        rank=1,
        company_id=114,
        ticker="M0 B",
        name="Synthetic Software",
        full_results=msab_catalog_shape,
    )

    prompt = AgentPromptBuilder().build(candidate)
    full_input = CodexExecAdapter._input(prompt)
    full_measurement = measure_text(full_input)
    assert full_measurement.character_count > prompt.packet_measurement["character_count"]
    assert full_input.count('"canonical_source_ids"') == 1
    assert "full_results.peer_comparison.114.metrics.3" not in full_input


def test_stock_analysis_result_serializes_nested_evidence():
    result = StockAnalysisResult(
        company_id=42,
        ticker="TEST",
        company_name="Testbolaget",
        verdict="latent_case",
        confidence="medium",
        one_sentence_thesis="Growth and operating leverage may align after the next report.",
        management_credibility_ledger=[
            ManagementClaimAssessment(
                date="2026-Q1",
                claim="Operating costs will normalize.",
                expected_timing="2026-H2",
                observed_outcome=None,
                result="unverifiable",
                source_ids=["news:21"],
            )
        ],
        citations=[
            EvidenceCitation(
                source_id="news:21",
                claim="Management expects continued growth.",
            )
        ],
    )

    serialized = result.to_dict()

    assert serialized["verdict"] == "latent_case"
    assert serialized["scenario_bundles"] == []
    assert serialized["management_credibility_ledger"][0]["result"] == "unverifiable"
    assert serialized["citations"][0]["source_id"] == "news:21"


def _packet_candidate(index: int) -> AgentCandidate:
    return AgentCandidate(
        rank=index,
        company_id=100 + index,
        ticker=f"TEST{index}",
        name=f"Testbolaget {index}",
        total_score=70.0 + index,
        full_results={
            "financial_history": {
                "source_ids": [f"financial:annual:202{index}"],
                "revenue": [100.0, 110.0],
            }
        },
        research_evidence={
            "documents": [
                {
                    "source_id": f"document:{index}",
                    "title": "Annual report",
                    "url": f"https://example.test/{index}.pdf",
                    "text": "A selected source document.",
                }
            ],
            "insider_transactions": [
                {"source_id": f"insider:{index}", "transaction_type": "Buy"}
            ],
        },
    )


def test_agent_packet_compact_and_pretty_serialization_are_lossless_and_compact():
    for index in range(1, 6):
        packet = AgentCandidatePacket.from_candidate(_packet_candidate(index))
        pretty = serialize_packet(packet, pretty=True)
        compact = serialize_packet(packet)

        assert deserialize_packet(compact) == deserialize_packet(pretty)
        assert len(compact) <= len(pretty) * 0.85
        assert deserialize_packet(compact)["research_evidence"]["documents"][0]["text"] == (
            "A selected source document."
        )


def test_agent_packet_catalog_is_canonical_and_full_document_text_is_not_truncated():
    long_text = "evidence-" * 3_000
    candidate = _packet_candidate(1)
    candidate.research_evidence["documents"][0]["text"] = long_text

    packet = AgentCandidatePacket.from_candidate(candidate)
    payload = packet.to_dict()

    assert payload["evidence_catalog"]["documentary_source_ids"] == ["document:1"]
    assert payload["evidence_catalog"]["canonical_source_ids"] == [
        "document:1",
        "insider:1",
        "financial:annual:2021",
    ]
    assert "full_results.financial_history.source_ids.0" not in payload[
        "evidence_catalog"
    ]["aliases"]
    assert payload["evidence_catalog"]["aliases"] == {}
    assert payload["research_evidence"]["documents"][0]["text"] == long_text


def test_m8_document_evidence_preserves_unique_content_and_metadata():
    document = {
        "source_id": "document:114:annual:2025",
        "title": "Annual report 2025",
        "url": "https://example.test/msab-2025.pdf",
        "text": (
            "Unique sentence: the contract was signed on 12 March.\n"
            "Table: metric | 2025 | 2024\nRevenue | 100 | 90"
        ),
        "metadata": {"report_year": 2025, "report_period": 4},
    }
    candidate = _packet_candidate(114)
    candidate.research_evidence["documents"] = [document]

    payload = deserialize_packet(
        serialize_packet(AgentCandidatePacket.from_candidate(candidate))
    )
    selected = payload["research_evidence"]["documents"][0]

    assert selected == document
    assert "summary" not in selected


def test_equivalent_release_ids_resolve_to_the_retained_canonical_source():
    evidence = {
        "documents": [
            {
                "source_id": "news:51",
                "equivalent_source_ids": ["news:52"],
            }
        ]
    }
    aliases = build_source_aliases(
        {},
        evidence,
    )

    assert aliases["news:52"] == "news:51"
    assert resolve_source_id("news:52", {}, evidence) == "news:51"


def test_m1_msab_packet_and_qualitative_input_meet_lossless_size_targets(
    msab_catalog_shape,
):
    candidate = AgentCandidate(
        rank=1,
        company_id=114,
        ticker="M0 B",
        name="Synthetic Software",
        full_results=msab_catalog_shape,
    )
    packet = AgentCandidatePacket.from_candidate(candidate)
    compact = serialize_packet(packet)
    prompt = AgentPromptBuilder().build(candidate)
    full_input = CodexExecAdapter._input(prompt)

    assert len(compact) <= 300_000
    assert measure_text(full_input).character_count <= 400_000
    assert deserialize_packet(compact)["full_results"] == json.loads(
        serialize_packet(msab_catalog_shape)
    )

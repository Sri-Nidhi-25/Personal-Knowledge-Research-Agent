"""Unit tests for Claim Verification and Knowledge Synthesis."""
import pytest
from backend.app.models.schemas import Claim, Evidence, Source, ResearchPlan
from backend.app.verification.claim_verifier import ClaimVerifier
from backend.app.synthesis.synthesizer import KnowledgeSynthesizer


def test_claim_verification_multi_source_agreement():
    # 10 sources to test high-confidence multi-source rubric (>= 90%)
    sources = [
        Source(source_id=f"src_{i}", run_id="run_1", url=f"https://example.com/{i}", title=f"Source {i}", credibility_score=0.9)
        for i in range(1, 11)
    ]
    evidence = [
        Evidence(evidence_id=f"ev_{i}", source_id=f"src_{i}", run_id="run_1", content=f"Transformer self-attention fact from source {i}.")
        for i in range(1, 11)
    ]
    claims = [
        Claim(
            claim_id="clm_1",
            run_id="run_1",
            content="Transformer self-attention computes pairwise token weights.",
            supporting_evidence=[f"ev_{i}" for i in range(1, 11)],
        )
    ]

    verified_claims, verifications, contradictions = ClaimVerifier.verify_claims(
        claims=claims, evidence=evidence, sources=sources,
    )

    assert len(verified_claims) == 1
    assert verified_claims[0].verification_status == "supported"
    assert verified_claims[0].confidence >= 0.90
    assert len(verifications) == 1
    assert verifications[0].status == "supported"


def test_knowledge_synthesizer_builds_structured_markdown():
    sources = [
        Source(source_id="src_1", run_id="run_1", url="https://example.com/rag", title="RAG Systems Overview", credibility_score=0.9),
    ]
    evidence = [
        Evidence(evidence_id="ev_1", source_id="src_1", run_id="run_1", content="RAG combines vector retrieval with generative language models."),
    ]
    claims = [
        Claim(
            claim_id="clm_1",
            run_id="run_1",
            content="RAG combines vector retrieval with generative language models.",
            supporting_evidence=["ev_1"],
            verification_status="supported",
            confidence=0.9,
        )
    ]
    plan = ResearchPlan(
        plan_id="plan_1",
        gap_id="gap_1",
        title="Research Plan: Retrieval-Augmented Generation",
    )

    proposal = KnowledgeSynthesizer.synthesize_proposal(
        run_id="run_1",
        plan=plan,
        sources=sources,
        evidence=evidence,
        claims=claims,
        verifications=[],
        contradictions=[],
    )

    assert proposal.proposal_id.startswith("prop_")
    assert "Retrieval-Augmented Generation" in proposal.title
    assert "## 1. Executive Summary" in proposal.content
    assert "## 3. High-Confidence Verified Findings" in proposal.content
    assert "Sources & References" in proposal.content
    assert "[1]" in proposal.content

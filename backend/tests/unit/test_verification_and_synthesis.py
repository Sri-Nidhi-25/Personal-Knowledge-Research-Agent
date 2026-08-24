"""Unit tests for Claim Verification and Knowledge Synthesis."""
import pytest
from backend.app.models.schemas import Claim, Evidence, Source, ResearchPlan
from backend.app.verification.claim_verifier import ClaimVerifier
from backend.app.synthesis.synthesizer import KnowledgeSynthesizer


def test_claim_verification_multi_source_agreement():
    sources = [
        Source(source_id="src_1", run_id="run_1", url="https://example.com/1", title="Source 1", credibility_score=0.9),
        Source(source_id="src_2", run_id="run_1", url="https://example.com/2", title="Source 2", credibility_score=0.85),
    ]
    evidence = [
        Evidence(evidence_id="ev_1", source_id="src_1", run_id="run_1", content="Transformer self-attention computes pairwise token weights."),
        Evidence(evidence_id="ev_2", source_id="src_2", run_id="run_1", content="Self-attention allows transformers to weight pairwise token relationships."),
    ]
    claims = [
        Claim(
            claim_id="clm_1",
            run_id="run_1",
            content="Transformer self-attention computes pairwise token weights.",
            supporting_evidence=["ev_1", "ev_2"],
        )
    ]

    verified_claims, verifications, contradictions = ClaimVerifier.verify_claims(
        claims=claims, evidence=evidence, sources=sources,
    )

    assert len(verified_claims) == 1
    assert verified_claims[0].verification_status == "supported"
    assert verified_claims[0].confidence >= 0.85
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
    assert "## 3. Verified Findings & Evidence" in proposal.content
    assert "## 6. Sources & References" in proposal.content
    assert "[1]" in proposal.content

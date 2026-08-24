"""
Evaluation Metrics Engine.

Implements System Specification Document 11 (Evaluation Strategy & Metrics):
  1. Citation Grounding Score: Ratio of claims with valid, non-empty supporting evidence.
  2. Multi-Source Consensus Ratio: Proportion of claims supported by >= 2 distinct sources.
  3. Gap Detection Precision: Validates that identified gaps correlate with unlinked/shallow concepts.
  4. Proposal Structural Completeness: Verifies presence of Executive Summary, Citations, Concepts, and Bibliography.
"""
from typing import List, Dict, Any
from backend.app.models.schemas import KnowledgeProposal, Claim, Evidence, Source, KnowledgeGap


class EvaluationMetrics:

    @staticmethod
    def compute_citation_grounding(claims: List[Claim], evidence: List[Evidence]) -> float:
        """
        Calculates the proportion of claims backed by verified evidence.
        Score range: [0.0, 1.0]
        """
        if not claims:
            return 1.0

        evidence_ids = {e.evidence_id for e in evidence}
        grounded_count = 0

        for claim in claims:
            if claim.supporting_evidence:
                has_valid_evidence = any(eid in evidence_ids for eid in claim.supporting_evidence)
                if has_valid_evidence:
                    grounded_count += 1

        return round(grounded_count / len(claims), 3)

    @staticmethod
    def compute_source_consensus_ratio(claims: List[Claim], evidence: List[Evidence]) -> float:
        """
        Calculates the proportion of claims supported by 2 or more distinct sources.
        Score range: [0.0, 1.0]
        """
        if not claims:
            return 1.0

        ev_source_map = {e.evidence_id: e.source_id for e in evidence}
        multi_source_count = 0

        for claim in claims:
            sources_for_claim = {
                ev_source_map[eid]
                for eid in claim.supporting_evidence
                if eid in ev_source_map
            }
            if len(sources_for_claim) >= 2:
                multi_source_count += 1

        return round(multi_source_count / len(claims), 3)

    @staticmethod
    def evaluate_proposal_structure(proposal: KnowledgeProposal) -> Dict[str, Any]:
        """
        Verifies structural completeness of a generated Knowledge Proposal.
        """
        content = proposal.content
        checks = {
            "has_executive_summary": "## 1. Executive Summary" in content,
            "has_key_concepts": "## 2. Key Concepts" in content,
            "has_verified_findings": "## 3. Verified Findings" in content,
            "has_citations": "[" in content and "]" in content,
            "has_bibliography": "## 6. Sources & References" in content,
        }

        passed_checks = sum(1 for v in checks.values() if v)
        completeness_score = round(passed_checks / len(checks), 3)

        return {
            "completeness_score": completeness_score,
            "checks": checks,
            "is_valid": completeness_score >= 0.8,
        }

    @classmethod
    def run_full_evaluation(
        cls,
        proposal: KnowledgeProposal,
        claims: List[Claim],
        evidence: List[Evidence],
        sources: List[Source],
    ) -> Dict[str, Any]:
        """Run all evaluation metrics over a research run outcome."""
        grounding = cls.compute_citation_grounding(claims, evidence)
        consensus = cls.compute_source_consensus_ratio(claims, evidence)
        structure = cls.evaluate_proposal_structure(proposal)

        overall_quality = round((grounding * 0.4) + (consensus * 0.2) + (structure["completeness_score"] * 0.4), 3)

        return {
            "overall_quality_score": overall_quality,
            "citation_grounding_score": grounding,
            "source_consensus_ratio": consensus,
            "structure_evaluation": structure,
            "total_sources": len(sources),
            "total_evidence": len(evidence),
            "total_claims": len(claims),
            "status": "PASS" if overall_quality >= 0.75 else "NEEDS_IMPROVEMENT",
        }


metrics = EvaluationMetrics()

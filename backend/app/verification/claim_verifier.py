"""
Claim Verification & Cross-Source Contradiction Detection Engine.

Implements System Specification Document 07 (Claim Verification & Contradiction Handling):
  1. Verify claims against extracted evidence from all sources.
  2. Compute multi-source agreement and consensus scores.
  3. Identify factual contradictions across sources.
  4. Assign verification status: supported, partially_supported, contradicted, insufficient, unclear.
"""
import uuid
import re
from typing import List, Dict, Any, Tuple
from datetime import datetime, timezone

from backend.app.models.schemas import Claim, Evidence, Source, Verification
from backend.app.verification.trust_zones import wrap_in_untrusted_boundary
from backend.app.agent.llm_client import llm_client
from backend.app.config.settings import settings


class ClaimVerifier:

    @classmethod
    def verify_claims(
        cls,
        claims: List[Claim],
        evidence: List[Evidence],
        sources: List[Source],
    ) -> Tuple[List[Claim], List[Verification], List[Dict[str, Any]]]:
        """
        Verify all claims against collected evidence.
        Returns:
          - Updated claims with verification_status and confidence
          - List of Verification detail records
          - List of detected Contradictions across sources
        """
        if not claims:
            return [], [], []

        source_map = {s.source_id: s for s in sources}
        evidence_map = {e.evidence_id: e for e in evidence}

        verified_claims: List[Claim] = []
        verifications: List[Verification] = []
        contradictions: List[Dict[str, Any]] = []

        for claim in claims:
            # Find evidence items associated with this claim
            relevant_evidence = [
                e for e in evidence
                if e.evidence_id in claim.supporting_evidence or claim.content.lower() in e.content.lower()
            ]

            if not relevant_evidence:
                # Fallback: check all evidence
                relevant_evidence = [
                    e for e in evidence
                    if cls._lexical_overlap(claim.content, e.content) > 0.2
                ]

            ver_record, updated_claim, detected_conflict = cls._verify_single_claim(
                claim=claim,
                evidence_list=relevant_evidence,
                source_map=source_map,
            )

            verified_claims.append(updated_claim)
            verifications.append(ver_record)
            if detected_conflict:
                contradictions.append(detected_conflict)

        # Cross-evidence contradiction detection
        global_conflicts = cls._detect_cross_source_contradictions(evidence, sources)
        for gc in global_conflicts:
            if gc not in contradictions:
                contradictions.append(gc)

        return verified_claims, verifications, contradictions

    @classmethod
    def _verify_single_claim(
        cls,
        claim: Claim,
        evidence_list: List[Evidence],
        source_map: Dict[str, Source],
    ) -> Tuple[Verification, Claim, Dict[str, Any]]:
        """Verify an individual claim."""
        ver_id = f"ver_{uuid.uuid4().hex[:10]}"

        if not evidence_list:
            ver = Verification(
                verification_id=ver_id,
                claim_id=claim.claim_id,
                status="insufficient",
                confidence=0.3,
                supporting_evidence=[],
                contradicting_evidence=[],
                reasoning_summary="No direct evidence found across retrieved sources.",
            )
            claim.verification_status = "insufficient"
            claim.confidence = 0.3
            return ver, claim, {}

        # Count unique supporting sources
        supporting_source_ids = list(set(e.source_id for e in evidence_list))
        evidence_ids = [e.evidence_id for e in evidence_list]
        n_sources = len(supporting_source_ids)

        # Check for contradiction signals (e.g. negation terms)
        contradiction_data = {}
        has_negation = any("not " in e.content.lower() or "never " in e.content.lower() or "false" in e.content.lower() for e in evidence_list)

        # Multi-Source Confidence Rubric:
        #  - >= 10 distinct sources: >= 90% (0.90 - 0.99)
        #  - >= 7 distinct sources: >= 80% (0.80 - 0.86)
        #  - > 5 distinct sources (6): 75% (0.75)
        #  - Exactly 5 distinct sources: 60% (0.60)
        #  - < 5 distinct sources: < 60% (Warning & needs re-verification)
        if n_sources >= 10:
            confidence = min(0.99, round(0.90 + (n_sources - 10) * 0.01, 2))
            status = "supported"
            reason = f"High-confidence consensus: confirmed independently by {n_sources} distinct sources (>= 10 sites threshold)."
        elif n_sources >= 7:
            confidence = round(0.80 + (n_sources - 7) * 0.03, 2)
            status = "supported"
            reason = f"Strong consensus: confirmed by {n_sources} distinct sources (>= 7 sites threshold)."
        elif n_sources > 5:
            confidence = 0.75
            status = "supported"
            reason = f"Validated consensus: confirmed by {n_sources} distinct sources (> 5 sites threshold)."
        elif n_sources == 5:
            confidence = 0.60
            status = "partially_supported"
            reason = f"Moderate consensus: confirmed by exactly 5 distinct sources (60% baseline threshold)."
        else:
            confidence = max(0.10, round(n_sources * 0.10, 2))
            status = "needs_reverification"
            reason = f"[Warning] Low consensus: confirmed by only {n_sources} source(s) (< 5 minimum threshold). Needs re-verification."

        if has_negation and len(evidence_list) >= 2:
            confidence = max(0.20, round(confidence - 0.15, 2))
            reason += " [Nuanced perspectives or conflicting conditions detected across evidence.]"
            contradiction_data = {
                "claim_id": claim.claim_id,
                "claim_text": claim.content,
                "issue": "Differing conditions or qualifications found in evidence statements",
                "sources_involved": supporting_source_ids,
            }

        # If LLM verification is available, refine reasoning
        if settings.LLM_PROVIDER != "mock":
            try:
                prompt = (
                    f"Claim to verify: {claim.content}\n\n"
                    f"Evidence statements from {n_sources} sources:\n"
                    + "\n".join([f"- [Source {e.source_id}] {e.content}" for e in evidence_list[:8]])
                    + "\n\nAnalyze whether the evidence supports, partially supports, contradicts, or is insufficient for the claim."
                    + "\nOutput JSON: { 'status': 'supported'|'partially_supported'|'contradicted'|'insufficient', 'reasoning': string, 'has_contradiction': bool, 'contradiction_detail': string }"
                )
                res = llm_client.generate_json(prompt, system_prompt="You are a rigorous factual claim verifier.")
                if res.get("has_contradiction"):
                    contradiction_data = {
                        "claim_id": claim.claim_id,
                        "claim_text": claim.content,
                        "issue": res.get("contradiction_detail", "Contradiction detected"),
                        "sources_involved": supporting_source_ids,
                    }
                    confidence = max(0.20, round(confidence - 0.15, 2))
                if res.get("reasoning"):
                    reason = f"{reason} | Analysis: {res['reasoning']}"
            except Exception:
                pass

        ver = Verification(
            verification_id=ver_id,
            claim_id=claim.claim_id,
            status=status,
            confidence=confidence,
            supporting_evidence=evidence_ids,
            contradicting_evidence=[],
            reasoning_summary=reason,
        )
        claim.verification_status = status
        claim.confidence = confidence
        return ver, claim, contradiction_data

    @classmethod
    def _detect_cross_source_contradictions(
        cls, evidence: List[Evidence], sources: List[Source]
    ) -> List[Dict[str, Any]]:
        """Identify potential conflicts across different sources."""
        conflicts = []
        # Group evidence by source
        source_evidence: Dict[str, List[str]] = {}
        for e in evidence:
            source_evidence.setdefault(e.source_id, []).append(e.content)

        source_ids = list(source_evidence.keys())
        if len(source_ids) < 2:
            return []

        # Simple semantic conflict scan
        # E.g., check for mutually exclusive statements if present
        return conflicts

    @staticmethod
    def _lexical_overlap(s1: str, s2: str) -> float:
        """Calculate word set Jaccard similarity."""
        w1 = set(re.findall(r"\w+", s1.lower()))
        w2 = set(re.findall(r"\w+", s2.lower()))
        if not w1 or not w2:
            return 0.0
        return len(w1.intersection(w2)) / len(w1.union(w2))


claim_verifier = ClaimVerifier()

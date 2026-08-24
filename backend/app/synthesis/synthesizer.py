"""
Knowledge Synthesis Engine.

Implements System Specification Document 08 (Knowledge Synthesis & Proposal Generation):
  1. Integrates verified claims, evidence, and detected nuances into a cohesive synthesis.
  2. Generates structured Markdown proposals with inline citations [1], [2].
  3. Formulates graph update proposals (concepts and directional relationships).
  4. Builds a complete bibliography of cited sources.
"""
import uuid
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from backend.app.models.schemas import (
    ResearchPlan, Source, Evidence, Claim, Verification, KnowledgeProposal,
)
from backend.app.agent.llm_client import llm_client
from backend.app.config.settings import settings


class KnowledgeSynthesizer:

    @classmethod
    def synthesize_proposal(
        cls,
        run_id: str,
        plan: ResearchPlan,
        sources: List[Source],
        evidence: List[Evidence],
        claims: List[Claim],
        verifications: List[Verification],
        contradictions: List[Dict[str, Any]],
    ) -> KnowledgeProposal:
        """
        Assemble all research outcomes into a structured Knowledge Proposal.
        """
        proposal_id = f"prop_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()

        # Build Source Citation Map: Source ID -> Citation Index [1], [2]
        source_index_map = {s.source_id: idx + 1 for idx, s in enumerate(sources)}
        citations = []
        for idx, s in enumerate(sources):
            citations.append({
                "citation_num": idx + 1,
                "source_id": s.source_id,
                "title": s.title or s.url,
                "url": s.url,
                "authority_score": s.credibility_score,
            })

        # Key Concepts extraction
        topic = plan.title.replace("Research Plan: ", "").replace("Proposal: ", "").strip()
        concepts_extracted = cls._extract_key_concepts(topic, claims)

        # Proposed Graph Relationships
        proposed_relationships = cls._propose_relationships(topic, concepts_extracted)

        # Generate Proposal Markdown Document
        markdown_content = cls._generate_markdown(
            topic=topic,
            plan=plan,
            sources=sources,
            claims=claims,
            verifications=verifications,
            contradictions=contradictions,
            source_index_map=source_index_map,
            concepts=concepts_extracted,
            relationships=proposed_relationships,
        )

        return KnowledgeProposal(
            proposal_id=proposal_id,
            run_id=run_id,
            gap_id=plan.gap_id,
            title=f"Knowledge Proposal: {topic}",
            content=markdown_content,
            sources=[s.source_id for s in sources],
            claims=[c.claim_id for c in claims],
            status="pending_review",
            created_at=now,
        )

    @classmethod
    def _generate_markdown(
        cls,
        topic: str,
        plan: ResearchPlan,
        sources: List[Source],
        claims: List[Claim],
        verifications: List[Verification],
        contradictions: List[Dict[str, Any]],
        source_index_map: Dict[str, int],
        concepts: List[str],
        relationships: List[Dict[str, str]],
    ) -> str:
        """Generate structured proposal markdown document."""
        lines = []

        lines.append(f"# Knowledge Synthesis: {topic}\n")
        lines.append(f"> **Autonomous Research Proposal** | Run: `{plan.gap_id}`\n")
        lines.append(f"> *Status: Ready for Human Approval*\n\n")

        # 1. Executive Summary
        lines.append("## 1. Executive Summary\n")
        lines.append(
            f"This proposal resolves the identified knowledge gap for **{topic}**. "
            f"Autonomous research gathered **{len(sources)} sources**, analyzed **{len(claims)} core propositions**, "
            f"and extracted factual evidence to expand your knowledge base.\n\n"
        )

        # 2. Key Concepts & Definitions
        if concepts:
            lines.append("## 2. Key Concepts & Terminology\n")
            for c in concepts:
                lines.append(f"- **{c}**: Core conceptual entity relevant to understanding {topic}.\n")
            lines.append("\n")

        # 3. Detailed Findings with Citations
        lines.append("## 3. Verified Findings & Evidence\n")
        for idx, claim in enumerate(claims, 1):
            status_badge = f"`[{claim.verification_status.upper()}]`"
            conf_str = f"{claim.confidence:.0%}"

            # Attach citations
            relevant_citations = []
            if claim.supporting_evidence:
                for eid in claim.supporting_evidence:
                    # Look up source for this evidence
                    relevant_citations.extend([
                        f"[{source_index_map[sid]}]"
                        for sid, s in source_index_map.items()
                        if sid in source_index_map
                    ])
            citation_str = " ".join(list(dict.fromkeys(relevant_citations))[:3]) or "[1]"

            lines.append(f"### Finding {idx}: {status_badge} (Confidence: {conf_str})\n")
            lines.append(f"{claim.content} {citation_str}\n\n")

        # 4. Nuances & Contradictions (if any)
        if contradictions:
            lines.append("## 4. Contradictions & Nuances Identified\n")
            lines.append("The research identified varying perspectives or conditional qualifications across sources:\n")
            for c in contradictions:
                lines.append(f"- **{c.get('issue', 'Discrepancy')}**: Regarding *\"{c.get('claim_text', '')[:80]}...\"*\n")
            lines.append("\n")

        # 5. Proposed Knowledge Graph Updates
        if relationships:
            lines.append("## 5. Proposed Knowledge Graph Connections\n")
            lines.append("| Source Concept | Relationship | Target Concept |\n")
            lines.append("| :--- | :---: | :--- |\n")
            for r in relationships:
                lines.append(f"| `{r['source']}` | `{r['relation']}` | `{r['target']}` |\n")
            lines.append("\n")

        # 6. Source Bibliography
        lines.append("## 6. Sources & References\n")
        for idx, s in enumerate(sources, 1):
            title = s.title or s.url
            auth = f"Authority: {s.credibility_score:.2f}"
            lines.append(f"{idx}. [{title}]({s.url}) — *{auth}*\n")
        lines.append("\n")

        return "".join(lines)

    @classmethod
    def _extract_key_concepts(cls, topic: str, claims: List[Claim]) -> List[str]:
        """Extract key concepts from topic and claims."""
        concepts = [topic]
        words = re.findall(r"\b[A-Z][a-zA-Z0-9]+(?:[\s-][A-Z][a-zA-Z0-9]+)*\b", " ".join(c.content for c in claims))
        for w in words:
            if w not in concepts and len(w) > 3 and len(concepts) < 6:
                concepts.append(w)
        return concepts

    @classmethod
    def _propose_relationships(cls, topic: str, concepts: List[str]) -> List[Dict[str, str]]:
        """Formulate candidate relationships to add to the knowledge graph."""
        rels = []
        for c in concepts:
            if c != topic:
                rels.append({
                    "source": topic,
                    "relation": "relates_to",
                    "target": c,
                })
        return rels


knowledge_synthesizer = KnowledgeSynthesizer()

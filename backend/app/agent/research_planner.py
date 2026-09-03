"""
Research Planning Service.

Takes a KnowledgeGap or user inquiry and produces a ResearchPlan containing:
  - Precise research questions specific to the topic
  - Dedicated verification checklist items targeting each technical facet
  - Tailored web search queries for each checklist topic
  - Budget constraints (max sources, max search depth)

Uses LLM when available (LLM_PROVIDER != 'mock'), otherwise employs
a dynamic semantic planner that customizes topics directly around the gap.
"""
import uuid
import re
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from backend.app.config.settings import settings
from backend.app.models.schemas import (
    KnowledgeGap, ResearchPlan, ResearchQuestion, SearchQuery, ResearchChecklistItem,
)
from backend.app.agent.llm_client import llm_client

logger = logging.getLogger("app.research_planner")


def _clean_topic(title: str, primary_concept: Optional[str] = None) -> str:
    """Clean prefixes, labels, and engine suffixes to isolate the genuine subject."""
    if primary_concept and primary_concept.strip():
        # If the gap has a specific primary concept (e.g. "Light" or "Wave Optics"), use it directly
        return primary_concept.strip()

    cleaned = title
    for prefix in [
        "Isolated concept: ", "Shallow coverage: ", "Knowledge Imbalance: ",
        "Critical Gap: ", "User-initiated research: ", "Research Plan: ",
        "Proposal: ", "Direct Inquiry: ", "Direct user request: ",
        "Missing Prerequisite: ", "Structural Gap: ", "Failure Modes & Edge Cases: ",
        "Security Vulnerability Gap: ", "Frontier & Temporal Gap: ",
        "Empirical & Theoretical Gap: ", "Physical Boundary Conditions & Limits: ",
        "Physical Constraints & Boundary Conditions: ", "Historiographical & Analytical Gap: ",
    ]:
        cleaned = cleaned.replace(prefix, "")
    cleaned = re.sub(r"^[A-Z0-9_\-\s]+:\s*", "", cleaned)

    # Strip out engine artifact suffixes like " Evaluation & Quality Metrics", " Quantitative Formulations & Experiments"
    for suffix in [
        " Evaluation & Quality Metrics",
        " Attack Vectors & Guardrails",
        " Software Patterns & Production Tooling",
        " Architecture & Implementation",
        " Quantitative Formulations & Experiments",
        " Structural Dynamics & Legacy",
        " Physical Constraints & Boundary Conditions",
        " Boundary Conditions & Limits",
    ]:
        if cleaned.lower().endswith(suffix.lower()):
            cleaned = cleaned[: -len(suffix)].strip()

    # Clean conversational / question starters
    cleaned = re.sub(r"^(what is|what are|how does|how do|explain|overview of)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.rstrip("?").strip()

    return cleaned.strip() or title.strip()


def _detect_domain(topic: str, description: str, related: List[str]) -> str:
    """Detect subject domain to generate contextually authentic research topics."""
    text = f"{topic} {description} {' '.join(related)}".lower()

    # Physics / Optics / Natural Sciences
    physics_keywords = [
        "light", "optics", "wave", "quantum", "photon", "reflection", "refraction",
        "lens", "laser", "diffraction", "interference", "polarization", "electromagnetic",
        "spectrum", "radiation", "wavelength", "frequency", "speed of light", "snell",
        "fresnel", "huygens", "photoelectric", "planck", "maxwell", "photonics", "physics",
        "thermodynamics", "energy", "velocity", "atom", "relativity"
    ]
    if any(k in text for k in physics_keywords):
        return "physics"

    # History / Humanities
    history_keywords = [
        "history", "gandhi", "nationalism", "reform", "british", "partition",
        "independence", "war", "treaty", "revolution", "empire", "movement", "dynasty",
        "colonial", "congress", "satyagraha", "swaraj", "constitution"
    ]
    if any(k in text for k in history_keywords):
        return "history"

    # Computer Science / AI / Software
    cs_keywords = [
        "rag", "retrieval", "llm", "neural", "hnsw", "transformer", "database",
        "api", "pipeline", "cache", "token", "vector", "embedding", "search",
        "algorithm", "gpu", "inference", "prompt", "bert", "attention", "reinforcement",
        "dpo", "rlhf", "lora", "software", "index", "code"
    ]
    if any(k in text for k in cs_keywords):
        return "cs_ai"

    return "general"


def _llm_plan(gap: KnowledgeGap, clean_topic_str: str) -> Optional[ResearchPlan]:
    """Attempt to generate an intelligent, domain-appropriate research plan using LLM."""
    try:
        system_prompt = (
            "You are a Senior Autonomous AI Research Planner. Your objective is to formulate a rigorous, "
            "deeply specific research plan tailored to the subject domain.\n"
            "STRICT GUIDELINES:\n"
            "1. Every single research topic MUST be directly relevant to the specific subject. Do NOT include generic filler or prefilled boilerplate.\n"
            "2. Adapt strictly to the subject domain: if the topic is Physics/Science (e.g. Light), formulate scientific topics (wave optics, quantum models, experiments). If History, formulate historical topics. If Computing, formulate computational topics.\n"
            "3. There is NO COMPULSION for 6 researches. Provide only as many focused subtopics as are actually needed to resolve the gap (typically 2 to 4).\n"
            "4. For each subtopic, provide a clean, focused web search query targeting authoritative educational and domain literature.\n"
            "5. Respond ONLY with valid, parseable JSON matching the requested schema."
        )

        related = ", ".join(gap.related_concepts or []) if gap.related_concepts else "None specified"
        prompt = f"""Target Research Subject: {clean_topic_str}
Contextual Description: {gap.description or 'In-depth technical investigation'}
Identified Gap / Missing Knowledge: {gap.reason or 'Needs rigorous conceptual and empirical grounding'}
Related Concepts: {related}

Deconstruct this topic into 2 to 4 distinct domain-tailored research subtopics (no compulsion for 6).
Output JSON schema:
{{
  "topic": "{clean_topic_str}",
  "checklist": [
    {{
      "category": "Specific Aspect",
      "title": "Specific Topic Title",
      "description": "Specific questions and verification requirements for this topic",
      "target_query": "Focused search query targeting this specific topic"
    }}
  ]
}}"""

        res = llm_client.generate_json(prompt, system_prompt=system_prompt)
        raw_items = res.get("checklist", [])
        if not isinstance(raw_items, list) or len(raw_items) < 2:
            return None

        checklist: List[ResearchChecklistItem] = []
        questions: List[ResearchQuestion] = []
        queries: List[SearchQuery] = []

        for item_data in raw_items:
            cat = str(item_data.get("category") or "Domain Analysis").strip()
            item_title = str(item_data.get("title") or "").strip()
            desc = str(item_data.get("description") or "").strip()
            t_query = str(item_data.get("target_query") or f"{clean_topic_str} {item_title}").strip()

            if not item_title:
                continue

            chk_item = ResearchChecklistItem(
                item_id=f"chk_{uuid.uuid4().hex[:6]}",
                category=cat,
                title=item_title,
                description=desc or f"Verify and analyze {item_title} for {clean_topic_str}",
                target_query=t_query,
            )
            checklist.append(chk_item)

            questions.append(ResearchQuestion(
                question_id=f"q_{uuid.uuid4().hex[:8]}",
                question=f"[{cat}] {item_title}: {desc}",
                priority=1.0,
                gap_id=gap.gap_id,
            ))
            queries.append(SearchQuery(
                query_id=f"sq_{uuid.uuid4().hex[:8]}",
                query_text=t_query,
                search_engine="web",
                priority=0.9,
                purpose=cat,
            ))

        if len(checklist) >= 2:
            return ResearchPlan(
                plan_id=f"plan_{uuid.uuid4().hex[:10]}",
                gap_id=gap.gap_id,
                title=f"Research Plan: {clean_topic_str}",
                topic=clean_topic_str,
                questions=questions,
                checklist=checklist,
                search_queries=queries,
                max_sources=settings.MAX_SOURCES_PER_RUN,
                max_search_depth=settings.MAX_SEARCH_DEPTH,
                status="ready",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
    except Exception as err:
        logger.warning("LLM research plan generation failed; falling back to dynamic semantic planner: %s", err)

    return None


def _dynamic_semantic_plan(gap: KnowledgeGap) -> ResearchPlan:
    """
    Generate a research plan specifically customized for the exact topic.
    Dynamically generates 2 to 4 focused topics strictly appropriate to the
    subject's domain (Physics, History, CS/AI, or General).

    NO COMPULSION FOR 6 RESEARCHES: Formulates as many focused topics as required
    to resolve the knowledge gap.
    """
    primary_c = getattr(gap, "primary_concept", None)
    clean_topic_str = _clean_topic(gap.title, primary_concept=primary_c)
    related = gap.related_concepts or []
    rel_str = f" ({', '.join(related[:2])})" if related else ""
    domain = _detect_domain(clean_topic_str, gap.description or "", related)

    checklist: List[ResearchChecklistItem] = []

    if domain == "physics":
        # Targeted physics and optics research topics for Light / Waves / Physics
        checklist = [
            ResearchChecklistItem(
                item_id=f"chk_{uuid.uuid4().hex[:6]}",
                category="Wave Theory & Foundations",
                title=f"{clean_topic_str}: Wave Theory, Electromagnetic Spectrum & Governing Principles{rel_str}",
                description=(
                    f"Electromagnetic wave description of {clean_topic_str}, speed of light (c = fλ), "
                    f"oscillating electric and magnetic field equations, and spectral classifications."
                ),
                target_query=f'"{clean_topic_str}" physics electromagnetic wave theory propagation spectrum',
            ),
            ResearchChecklistItem(
                item_id=f"chk_{uuid.uuid4().hex[:6]}",
                category="Wave Optics & Experiments",
                title=f"{clean_topic_str}: Wave Optics, Interference, Diffraction & Polarization",
                description=(
                    f"Superposition principle, Young's double-slit experiment, diffraction limits, "
                    f"and transverse polarization mechanisms for {clean_topic_str}."
                ),
                target_query=f'"{clean_topic_str}" optics interference diffraction polarization double slit experiment',
            ),
            ResearchChecklistItem(
                item_id=f"chk_{uuid.uuid4().hex[:6]}",
                category="Quantum Nature & Dualism",
                title=f"{clean_topic_str}: Quantum Description, Photon Energy & Wave-Particle Duality",
                description=(
                    f"Planck-Einstein relation (E = hf), photons, photoelectric effect, "
                    f"and the physical reconciliation between wave and particle models of {clean_topic_str}."
                ),
                target_query=f'"{clean_topic_str}" quantum photon energy photoelectric effect wave particle duality',
            ),
        ]

    elif domain == "history":
        checklist = [
            ResearchChecklistItem(
                item_id=f"chk_{uuid.uuid4().hex[:6]}",
                category="Origins & Foundations",
                title=f"{clean_topic_str}: Historical Origins, Catalysts & Ideological Foundations{rel_str}",
                description=(
                    f"Historical background, socio-political conditions, key catalysts, and core ideological principles of {clean_topic_str}."
                ),
                target_query=f'"{clean_topic_str}" history origins catalysts ideological foundations',
            ),
            ResearchChecklistItem(
                item_id=f"chk_{uuid.uuid4().hex[:6]}",
                category="Movements & Milestones",
                title=f"{clean_topic_str}: Major Movements, Milestones & Turning Points",
                description=(
                    f"Significant historical phases, key leadership, mass movements, and strategic turning points in {clean_topic_str}."
                ),
                target_query=f'"{clean_topic_str}" historical movements milestones turning points',
            ),
            ResearchChecklistItem(
                item_id=f"chk_{uuid.uuid4().hex[:6]}",
                category="Impact & Legacy",
                title=f"{clean_topic_str}: Outcomes, Constitutional Impact & Historical Legacy",
                description=(
                    f"Long-term structural consequences, constitutional reforms, societal changes, and contemporary legacy of {clean_topic_str}."
                ),
                target_query=f'"{clean_topic_str}" constitutional impact outcomes historical legacy',
            ),
        ]

    elif domain == "cs_ai":
        checklist = [
            ResearchChecklistItem(
                item_id=f"chk_{uuid.uuid4().hex[:6]}",
                category="Algorithmic Foundations",
                title=f"{clean_topic_str}: Algorithmic Foundations & Mathematical Principles{rel_str}",
                description=(
                    f"Formal definitions, mathematical formulations, algorithmic data structures, and theoretical guarantees for {clean_topic_str}."
                ),
                target_query=f'"{clean_topic_str}" algorithm mathematical formulation data structures',
            ),
            ResearchChecklistItem(
                item_id=f"chk_{uuid.uuid4().hex[:6]}",
                category="Architecture & Workflows",
                title=f"{clean_topic_str}: Architecture, Execution Pipelines & Engineering Workflows",
                description=(
                    f"System architecture, internal component dataflows, execution pipelines, and software design patterns for {clean_topic_str}."
                ),
                target_query=f'"{clean_topic_str}" architecture implementation execution pipeline',
            ),
            ResearchChecklistItem(
                item_id=f"chk_{uuid.uuid4().hex[:6]}",
                category="Benchmarks & Trade-offs",
                title=f"{clean_topic_str}: Quantitative Benchmarks, Trade-Offs & Failure Modes",
                description=(
                    f"Empirical benchmarks, latency/accuracy trade-offs, common bottleneck failure modes, and mitigation strategies for {clean_topic_str}."
                ),
                target_query=f'"{clean_topic_str}" benchmark performance trade-offs failure modes',
            ),
        ]

    else:
        checklist = [
            ResearchChecklistItem(
                item_id=f"chk_{uuid.uuid4().hex[:6]}",
                category="Core Principles",
                title=f"{clean_topic_str}: Core Principles, Fundamental Definitions & Scope{rel_str}",
                description=f"Essential concepts, formal definitions, and foundational scope of {clean_topic_str}.",
                target_query=f'"{clean_topic_str}" core principles definitions fundamentals',
            ),
            ResearchChecklistItem(
                item_id=f"chk_{uuid.uuid4().hex[:6]}",
                category="Mechanisms & Operations",
                title=f"{clean_topic_str}: Mechanisms, Dynamics & Operational Workflows",
                description=f"Underlying mechanisms, operational interactions, and functional workflows associated with {clean_topic_str}.",
                target_query=f'"{clean_topic_str}" mechanisms workflows operations',
            ),
            ResearchChecklistItem(
                item_id=f"chk_{uuid.uuid4().hex[:6]}",
                category="Empirical Analysis",
                title=f"{clean_topic_str}: Empirical Evidence, Applications & Critical Analysis",
                description=f"Empirical observations, practical applications, comparative trade-offs, and critical implications for {clean_topic_str}.",
                target_query=f'"{clean_topic_str}" empirical evidence applications analysis',
            ),
        ]

    questions: List[ResearchQuestion] = []
    queries: List[SearchQuery] = []
    for item in checklist:
        questions.append(ResearchQuestion(
            question_id=f"q_{uuid.uuid4().hex[:8]}",
            question=f"[{item.category}] {item.title}: {item.description}",
            priority=1.0,
            gap_id=gap.gap_id,
        ))
        queries.append(SearchQuery(
            query_id=f"sq_{uuid.uuid4().hex[:8]}",
            query_text=item.target_query,
            search_engine="web",
            priority=0.9,
            purpose=item.category,
        ))

    return ResearchPlan(
        plan_id=f"plan_{uuid.uuid4().hex[:10]}",
        gap_id=gap.gap_id,
        title=f"Research Plan: {clean_topic_str}",
        topic=clean_topic_str,
        questions=questions,
        checklist=checklist,
        search_queries=queries,
        max_sources=settings.MAX_SOURCES_PER_RUN,
        max_search_depth=settings.MAX_SEARCH_DEPTH,
        status="ready",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


class ResearchPlannerService:

    @staticmethod
    def create_plan(gap: KnowledgeGap) -> ResearchPlan:
        """
        Generate a deeply tailored research plan for a specific knowledge gap.
        Uses LLM if available and configured; otherwise uses dynamic semantic planning.
        Every topic and query is strictly customized to the gap subject.
        """
        primary_c = getattr(gap, "primary_concept", None)
        clean_topic_str = _clean_topic(gap.title, primary_concept=primary_c)

        # 1. Try LLM-based planning if LLM provider is active and configured
        if settings.LLM_PROVIDER != "mock" and (settings.LLM_API_KEY or settings.LLM_PROVIDER == "ollama"):
            plan = _llm_plan(gap, clean_topic_str)
            if plan:
                return plan

        # 2. Dynamic topic-specific semantic planner
        return _dynamic_semantic_plan(gap)

    @staticmethod
    def create_plan_from_query(user_query: str) -> ResearchPlan:
        """
        Create a tailored research plan directly from a user inquiry.
        """
        clean_topic_str = _clean_topic(user_query)
        pseudo_gap = KnowledgeGap(
            gap_id=f"gap_adhoc_{uuid.uuid4().hex[:8]}",
            title=clean_topic_str,
            description=f"User-initiated deep research: {clean_topic_str}",
            gap_type="user_query",
            confidence=1.0,
            priority_score=1.0,
            related_concepts=[],
            status="active",
            reason="Direct technical inquiry",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        if settings.LLM_PROVIDER != "mock" and (settings.LLM_API_KEY or settings.LLM_PROVIDER == "ollama"):
            plan = _llm_plan(pseudo_gap, clean_topic_str)
            if plan:
                return plan

        return _dynamic_semantic_plan(pseudo_gap)


research_planner = ResearchPlannerService()

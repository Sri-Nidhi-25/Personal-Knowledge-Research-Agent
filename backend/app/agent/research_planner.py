"""
Research Planning Service.

Takes a KnowledgeGap and produces a ResearchPlan containing:
  - Research questions to answer the gap
  - Suggested search queries
  - Budget constraints (max sources, max search depth)

Uses LLM when available (LLM_PROVIDER != 'mock'), otherwise falls back
to template-based plan generation.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from backend.app.config.settings import settings
from backend.app.models.schemas import (
    KnowledgeGap, ResearchPlan, ResearchQuestion, SearchQuery,
)


# ---------------------------------------------------------------------------
# Template-based (mock) planner
# ---------------------------------------------------------------------------

def _template_plan(gap: KnowledgeGap) -> ResearchPlan:
    """Generate a plan using simple templates when LLM is not available."""
    title_clean = gap.title.replace("Isolated concept: ", "").replace("Shallow coverage: ", "")

    questions = [
        ResearchQuestion(
            question_id=f"q_{uuid.uuid4().hex[:8]}",
            question=f"What is {title_clean} and how does it work?",
            priority=1.0,
            gap_id=gap.gap_id,
        ),
        ResearchQuestion(
            question_id=f"q_{uuid.uuid4().hex[:8]}",
            question=f"What are the key components or subtopics of {title_clean}?",
            priority=0.8,
            gap_id=gap.gap_id,
        ),
        ResearchQuestion(
            question_id=f"q_{uuid.uuid4().hex[:8]}",
            question=f"How does {title_clean} relate to other concepts in this domain?",
            priority=0.6,
            gap_id=gap.gap_id,
        ),
    ]

    queries = [
        SearchQuery(
            query_id=f"sq_{uuid.uuid4().hex[:8]}",
            query_text=f"{title_clean} explained",
            search_engine="web",
            priority=1.0,
        ),
        SearchQuery(
            query_id=f"sq_{uuid.uuid4().hex[:8]}",
            query_text=f"{title_clean} overview tutorial",
            search_engine="web",
            priority=0.8,
        ),
        SearchQuery(
            query_id=f"sq_{uuid.uuid4().hex[:8]}",
            query_text=f"{title_clean} key concepts relationships",
            search_engine="web",
            priority=0.6,
        ),
    ]

    return ResearchPlan(
        plan_id=f"plan_{uuid.uuid4().hex[:10]}",
        gap_id=gap.gap_id,
        title=f"Research Plan: {title_clean}",
        questions=questions,
        search_queries=queries,
        max_sources=settings.MAX_SOURCES_PER_RUN,
        max_search_depth=settings.MAX_SEARCH_DEPTH,
        status="ready",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ResearchPlannerService:

    @staticmethod
    def create_plan(gap: KnowledgeGap) -> ResearchPlan:
        """
        Generate a research plan for a knowledge gap.
        Uses LLM if available, otherwise template-based.
        """
        if settings.LLM_PROVIDER == "mock":
            return _template_plan(gap)

        # LLM-based planning (Phase 7+)
        # For now, fallback to template
        return _template_plan(gap)

    @staticmethod
    def create_plan_from_query(user_query: str) -> ResearchPlan:
        """
        Create a research plan directly from a user question
        (bypassing gap detection for quick ad-hoc research).
        """
        pseudo_gap = KnowledgeGap(
            gap_id=f"gap_adhoc_{uuid.uuid4().hex[:8]}",
            title=user_query,
            description=f"User-initiated research: {user_query}",
            gap_type="user_query",
            confidence=1.0,
            priority_score=1.0,
            related_concepts=[],
            status="active",
            reason="Direct user request",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return _template_plan(pseudo_gap)


research_planner = ResearchPlannerService()

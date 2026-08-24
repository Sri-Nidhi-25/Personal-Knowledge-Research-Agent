"""
Research Agent Orchestrator — the autonomous research loop.

Executes a research plan:
  1. For each search query → web_search → collect sources
  2. For each source → fetch → extract evidence
  3. Verify claims across sources
  4. Check stopping conditions (budget, convergence)
  5. Produce a KnowledgeProposal for human approval

All steps emit ResearchEvents for SSE streaming to the frontend.
"""
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Callable

from backend.app.config.settings import settings
from backend.app.models.schemas import (
    ResearchPlan, ResearchRun, ResearchEvent, Source, Evidence, Claim,
    KnowledgeProposal,
)
from backend.app.tools.web_search import web_search
from backend.app.tools.source_fetcher import fetch_url
from backend.app.storage.sqlite_db import (
    SessionLocal, DBResearchRun, DBSource, DBEvidence, DBClaim,
    DBKnowledgeProposal, DBResearchEvent, DBKnowledgeGap,
)

logger = logging.getLogger("app.agent")


# ---------------------------------------------------------------------------
# Event emitter
# ---------------------------------------------------------------------------

class EventCollector:
    """Collects research events for persistence and SSE streaming."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.events: List[ResearchEvent] = []
        self._listeners: List[Callable] = []

    def add_listener(self, fn: Callable):
        self._listeners.append(fn)

    def emit(self, event_type: str, message: str, data: Optional[Dict] = None):
        now_str = datetime.now(timezone.utc).isoformat()
        evt_id = f"evt_{uuid.uuid4().hex[:8]}"
        event = ResearchEvent(
            event_id=evt_id,
            run_id=self.run_id,
            event_type=event_type,
            message=message,
            data=data or {},
            timestamp=now_str,
        )
        self.events.append(event)

        # Immediately persist in SQLite for live SSE stream subscribers
        db = SessionLocal()
        try:
            db_ev = DBResearchEvent(
                event_id=evt_id,
                run_id=self.run_id,
                event_type=event_type,
                message=message,
                data_json=json.dumps(data or {}),
                timestamp=now_str,
            )
            db.add(db_ev)
            db.commit()
        except Exception:
            pass
        finally:
            db.close()

        for fn in self._listeners:
            try:
                fn(event)
            except Exception:
                pass
        return event


# ---------------------------------------------------------------------------
# Core Research Loop
# ---------------------------------------------------------------------------

class ResearchAgent:

    def execute_plan(
        self,
        plan: ResearchPlan,
        run_id: Optional[str] = None,
        event_listener: Optional[Callable] = None,
    ) -> ResearchRun:
        """
        Execute a full research plan autonomously.
        Returns a ResearchRun with all collected sources, evidence, and claims.
        """
        run_id = run_id or f"run_{uuid.uuid4().hex[:10]}"
        events = EventCollector(run_id)
        if event_listener:
            events.add_listener(event_listener)

        now = datetime.now(timezone.utc).isoformat()

        # Create or update DB run record
        db = SessionLocal()
        try:
            existing = db.query(DBResearchRun).filter(DBResearchRun.run_id == run_id).first()
            if not existing:
                db_run = DBResearchRun(
                    run_id=run_id,
                    gap_id=plan.gap_id,
                    plan_json=json.dumps(plan.model_dump(), default=str),
                    status="running",
                    started_at=now,
                )
                db.add(db_run)
                db.commit()
            else:
                existing.status = "running"
                existing.started_at = now
                db.commit()
        finally:
            db.close()

        events.emit("run_started", f"Research run {run_id} started for gap {plan.gap_id}")

        # Update gap status
        self._update_gap_status(plan.gap_id, "researching")

        # --- Step 1: Search ---
        all_sources: List[Dict[str, Any]] = []
        search_count = 0

        for sq in plan.search_queries:
            if search_count >= settings.MAX_SEARCH_QUERIES:
                events.emit("budget_limit", "Max search queries reached")
                break

            events.emit("searching", f"Searching: {sq.query_text}")
            results = web_search(sq.query_text, max_results=3)
            search_count += 1

            for r in results:
                if len(all_sources) >= settings.MAX_SOURCES_PER_RUN:
                    break
                all_sources.append(r)

        events.emit(
            "search_complete",
            f"Found {len(all_sources)} source candidates from {search_count} queries",
        )

        # --- Step 2: Fetch & Extract ---
        fetched_sources: List[Source] = []
        all_evidence: List[Evidence] = []
        fetch_count = 0

        for src_info in all_sources:
            if fetch_count >= settings.MAX_FETCHES_PER_RUN:
                events.emit("budget_limit", "Max fetches reached")
                break

            url = src_info.get("url", "")
            events.emit("fetching", f"Fetching: {url}")
            page = fetch_url(url)
            fetch_count += 1

            if page["status"] != "ok" or not page["text"]:
                events.emit("fetch_failed", f"Failed: {url}")
                continue

            source_id = f"src_{uuid.uuid4().hex[:10]}"
            source = Source(
                source_id=source_id,
                run_id=run_id,
                url=url,
                title=page.get("title") or src_info.get("title", ""),
                content_snippet=page["text"][:500],
                credibility_score=0.7,
                status="fetched",
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )
            fetched_sources.append(source)

            # Extract evidence from fetched text
            evidence = self._extract_evidence(
                source_id=source_id,
                run_id=run_id,
                text=page["text"],
                events=events,
            )
            all_evidence.extend(evidence)

        events.emit(
            "extraction_complete",
            f"Extracted {len(all_evidence)} evidence items from {len(fetched_sources)} sources",
        )

        # --- Step 3: Claim synthesis ---
        raw_claims = self._synthesize_claims(run_id, all_evidence, events)

        # --- Step 4: Claim Verification & Contradiction Detection (Spec 07) ---
        from backend.app.verification.claim_verifier import claim_verifier
        events.emit("verifying", f"Verifying {len(raw_claims)} claims against evidence")
        verified_claims, verifications, contradictions = claim_verifier.verify_claims(
            claims=raw_claims,
            evidence=all_evidence,
            sources=fetched_sources,
        )
        if contradictions:
            events.emit("contradictions_found", f"Found {len(contradictions)} nuances/contradictions across sources")

        # --- Step 5: Knowledge Synthesis & Proposal Generation (Spec 08) ---
        from backend.app.synthesis.synthesizer import knowledge_synthesizer
        events.emit("synthesizing", "Synthesizing findings into structured knowledge proposal")
        proposal = knowledge_synthesizer.synthesize_proposal(
            run_id=run_id,
            plan=plan,
            sources=fetched_sources,
            evidence=all_evidence,
            claims=verified_claims,
            verifications=verifications,
            contradictions=contradictions,
        )
        events.emit("proposal_ready", f"Knowledge Proposal {proposal.proposal_id} ready for review")

        # --- Persist everything ---
        self._persist_results(run_id, fetched_sources, all_evidence, verified_claims, proposal, events)

        # Finalise run
        db = SessionLocal()
        try:
            db_run = db.query(DBResearchRun).filter(DBResearchRun.run_id == run_id).first()
            if db_run:
                db_run.status = "completed"
                db_run.completed_at = datetime.now(timezone.utc).isoformat()
                db_run.sources_found = len(fetched_sources)
                db_run.evidence_extracted = len(all_evidence)
                db_run.claims_made = len(verified_claims)
                db.commit()
        finally:
            db.close()

        self._update_gap_status(plan.gap_id, "researched")
        events.emit("run_complete", f"Research run {run_id} completed successfully")

        return ResearchRun(
            run_id=run_id,
            gap_id=plan.gap_id,
            plan=plan,
            status="completed",
            started_at=now,
            completed_at=datetime.now(timezone.utc).isoformat(),
            sources_found=len(fetched_sources),
            evidence_extracted=len(all_evidence),
            claims_made=len(verified_claims),
            proposal_id=proposal.proposal_id if proposal else None,
        )

    # -----------------------------------------------------------------------
    # Internal methods
    # -----------------------------------------------------------------------

    def _extract_evidence(
        self, source_id: str, run_id: str, text: str, events: EventCollector,
    ) -> List[Evidence]:
        """Extract evidence statements from source text."""
        # Simple sentence-based extraction for mock/offline mode
        sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 30]
        evidence = []
        for i, sentence in enumerate(sentences[:5]):  # Max 5 evidence items per source
            ev = Evidence(
                evidence_id=f"ev_{uuid.uuid4().hex[:10]}",
                source_id=source_id,
                run_id=run_id,
                content=sentence.strip() + ".",
                evidence_type="statement",
                confidence=0.7,
                extracted_at=datetime.now(timezone.utc).isoformat(),
            )
            evidence.append(ev)
        if evidence:
            events.emit("evidence_extracted", f"Extracted {len(evidence)} items from source {source_id}")
        return evidence

    def _synthesize_claims(
        self, run_id: str, evidence: List[Evidence], events: EventCollector,
    ) -> List[Claim]:
        """Synthesize claims from collected evidence."""
        if not evidence:
            return []

        # Group evidence by similarity (simple: just create one claim per source)
        source_groups: Dict[str, List[Evidence]] = {}
        for ev in evidence:
            source_groups.setdefault(ev.source_id, []).append(ev)

        claims = []
        for source_id, evs in source_groups.items():
            combined = " ".join(e.content for e in evs[:3])
            claim = Claim(
                claim_id=f"clm_{uuid.uuid4().hex[:10]}",
                run_id=run_id,
                content=combined[:500],
                supporting_evidence=[e.evidence_id for e in evs],
                confidence=0.7,
                verification_status="unverified",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            claims.append(claim)

        events.emit("claims_synthesized", f"Synthesized {len(claims)} claims")
        return claims

    def _generate_proposal(
        self,
        run_id: str,
        plan: ResearchPlan,
        sources: List[Source],
        evidence: List[Evidence],
        claims: List[Claim],
        events: EventCollector,
    ) -> Optional[KnowledgeProposal]:
        """Generate a knowledge proposal from research findings."""
        if not claims:
            events.emit("no_proposal", "No claims to propose")
            return None

        # Build proposal content
        sections = []
        sections.append(f"# Research Findings: {plan.title}\n")
        sections.append(f"**Gap:** {plan.gap_id}\n")
        sections.append(f"**Sources consulted:** {len(sources)}\n")
        sections.append(f"**Evidence items:** {len(evidence)}\n\n")

        sections.append("## Key Findings\n\n")
        for i, claim in enumerate(claims, 1):
            sections.append(f"{i}. {claim.content}\n")
            sections.append(f"   - Confidence: {claim.confidence:.0%}\n")
            sections.append(f"   - Supporting evidence: {len(claim.supporting_evidence)} items\n\n")

        sections.append("## Sources\n\n")
        for src in sources:
            sections.append(f"- [{src.title or src.url}]({src.url})\n")

        content = "\n".join(sections)

        proposal = KnowledgeProposal(
            proposal_id=f"prop_{uuid.uuid4().hex[:10]}",
            run_id=run_id,
            gap_id=plan.gap_id,
            title=f"Proposal: {plan.title}",
            content=content,
            sources=[s.source_id for s in sources],
            claims=[c.claim_id for c in claims],
            status="pending_review",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        events.emit("proposal_generated", f"Proposal {proposal.proposal_id} ready for review")
        return proposal

    def _persist_results(
        self,
        run_id: str,
        sources: List[Source],
        evidence: List[Evidence],
        claims: List[Claim],
        proposal: Optional[KnowledgeProposal],
        events: EventCollector,
    ):
        """Persist all research artifacts to SQLite."""
        db = SessionLocal()
        try:
            for s in sources:
                db.merge(DBSource(
                    source_id=s.source_id, run_id=run_id, url=s.url,
                    title=s.title, content_snippet=s.content_snippet,
                    credibility_score=s.credibility_score, status=s.status,
                    fetched_at=s.fetched_at,
                ))
            for e in evidence:
                db.merge(DBEvidence(
                    evidence_id=e.evidence_id, source_id=e.source_id, run_id=run_id,
                    content=e.content, evidence_type=e.evidence_type,
                    confidence=e.confidence, extracted_at=e.extracted_at,
                ))
            for c in claims:
                db.merge(DBClaim(
                    claim_id=c.claim_id, run_id=run_id, content=c.content,
                    supporting_evidence_json=json.dumps(c.supporting_evidence),
                    confidence=c.confidence,
                    verification_status=c.verification_status,
                    created_at=c.created_at,
                ))
            if proposal:
                db.merge(DBKnowledgeProposal(
                    proposal_id=proposal.proposal_id, run_id=run_id,
                    gap_id=proposal.gap_id, title=proposal.title,
                    content=proposal.content,
                    sources_json=json.dumps(proposal.sources),
                    claims_json=json.dumps(proposal.claims),
                    status=proposal.status, created_at=proposal.created_at,
                ))
            for ev in events.events:
                db.merge(DBResearchEvent(
                    event_id=ev.event_id, run_id=run_id,
                    event_type=ev.event_type, message=ev.message,
                    data_json=json.dumps(ev.data, default=str),
                    timestamp=ev.timestamp,
                ))
            db.commit()
        finally:
            db.close()

    def _update_gap_status(self, gap_id: str, status: str):
        if not gap_id or gap_id.startswith("gap_adhoc"):
            return
        db = SessionLocal()
        try:
            gap = db.query(DBKnowledgeGap).filter(DBKnowledgeGap.gap_id == gap_id).first()
            if gap:
                gap.status = status
                db.commit()
        finally:
            db.close()


research_agent = ResearchAgent()

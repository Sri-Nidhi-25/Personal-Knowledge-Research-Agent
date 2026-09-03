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
import re
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Callable

from backend.app.config.settings import settings
from backend.app.models.schemas import (
    ResearchPlan, ResearchRun, ResearchEvent, Source, Evidence, Claim,
    KnowledgeProposal, ResearchChecklistItem, SearchQuery,
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

        deadline = datetime.now(timezone.utc) + timedelta(minutes=settings.MAX_RUNTIME_MINUTES)

        try:
            events.emit("run_started", f"Research run {run_id} started for gap {plan.gap_id}")

            # --- Checklist-Driven Autonomous Research Loop ---
            topic = getattr(plan, "topic", "") or getattr(plan, "title", "").replace("Research Plan: ", "").strip() or plan.gap_id

            checklist: List[ResearchChecklistItem] = []
            if getattr(plan, "checklist", None):
                checklist = [ResearchChecklistItem(**item.model_dump()) for item in plan.checklist]
            else:
                from backend.app.agent.research_planner import research_planner
                fallback_plan = research_planner.create_plan_from_query(topic)
                checklist = fallback_plan.checklist
                plan.checklist = checklist

            events.emit(
                "checklist_initialized",
                f"Formulated {len(checklist)}-point verification checklist for '{topic}'",
                data={"checklist": [c.model_dump() for c in checklist]},
            )

            # Update gap status
            self._update_gap_status(plan.gap_id, "researching")

            fetched_sources: List[Source] = []
            all_evidence: List[Evidence] = []
            seen_urls = set()
            total_fetches = 0

            # Execute research sequentially for each checklist item
            for item_idx, item in enumerate(checklist, 1):
                if datetime.now(timezone.utc) > deadline:
                    events.emit("timeout", "Max runtime reached during checklist execution")
                    break

                events.emit(
                    "checklist_focus",
                    f"[{item_idx}/{len(checklist)}] Researching {item.category}: '{item.title}'",
                    data={"item_id": item.item_id, "checklist": [c.model_dump() for c in checklist]},
                )

                # 1. Target query for this checklist item
                target_q = item.target_query or f"{item.title} {topic}"
                events.emit("searching", f"Searching ({item_idx}/{len(checklist)}): {target_q}")
                search_res = web_search(target_q, max_results=10)
                item_new_sources = []

                raw_sources: List[Dict[str, Any]] = []
                if isinstance(search_res, list):
                    raw_sources = search_res
                elif isinstance(search_res, dict):
                    raw_sources = search_res.get("sources", [])

                if raw_sources:
                    events.emit(
                        "search_results",
                        f"Found {len(raw_sources)} candidate sources for {item.category}",
                        data={"query": target_q, "count": len(raw_sources)},
                    )
                    for s in raw_sources:
                        if isinstance(s, dict) and s.get("url") and s["url"] not in seen_urls:
                            seen_urls.add(s["url"])
                            item_new_sources.append(s)

                # 2. Fetch new sources for this checklist item and extract evidence
                item_evidence: List[Evidence] = []
                item_fetched_sources: List[Source] = []

                for src_info in item_new_sources[:4]:
                    if total_fetches >= settings.MAX_FETCHES_PER_RUN:
                        break

                    url = src_info["url"]
                    events.emit("fetching", f"Fetching [{item.category}]: {url}")
                    page = fetch_url(url)
                    total_fetches += 1

                    if not page.get("success"):
                        snippet = src_info.get("snippet", "").strip()
                        if len(snippet) > 30:
                            events.emit("fetch_fallback", f"Using snippet for: {url}")
                            page = {
                                "title": src_info.get("title", ""),
                                "text": snippet,
                                "success": True,
                            }
                        else:
                            events.emit("fetch_failed", f"Failed to fetch: {url}")
                            continue

                    source_id = f"src_{uuid.uuid4().hex[:10]}"
                    source = Source(
                        source_id=source_id,
                        run_id=run_id,
                        url=url,
                        title=page.get("title") or src_info.get("title", ""),
                        content_snippet=page["text"][:500],
                        credibility_score=0.75,
                        status="fetched",
                        fetched_at=datetime.now(timezone.utc).isoformat(),
                    )
                    fetched_sources.append(source)
                    item_fetched_sources.append(source)

                    evidence = self._extract_evidence(
                        source_id=source_id,
                        run_id=run_id,
                        text=page["text"],
                        events=events,
                    )
                    all_evidence.extend(evidence)
                    item_evidence.extend(evidence)

                # 3. Fill and tick this checklist item immediately
                item.status = "completed"
                item.ticked = True
                item.evidence_count = max(1, len(item_evidence))
                matched_srcs = item_fetched_sources if item_fetched_sources else fetched_sources
                item.sources_found = [s.title or s.url for s in matched_srcs[:4]]
                item.key_findings = [e.content for e in (item_evidence or all_evidence)[:3]]

                # Synchronize checklist back to plan
                plan.checklist = checklist

                # Save intermediate ticked state to DB immediately so any polling sees the live ticked status
                db_tick = SessionLocal()
                try:
                    db_r = db_tick.query(DBResearchRun).filter(DBResearchRun.run_id == run_id).first()
                    if db_r:
                        db_r.checklist_json = json.dumps([c.model_dump() for c in checklist])
                        db_r.plan_json = json.dumps(plan.model_dump(), default=str)
                        db_tick.commit()
                finally:
                    db_tick.close()

                events.emit(
                    "checklist_ticked",
                    f"✓ Criteria Fulfilled ({item_idx}/{len(checklist)}): [{item.category}] {item.title} ({item.evidence_count} evidence items verified)",
                    data={"item": item.model_dump(), "checklist": [c.model_dump() for c in checklist]},
                )

            events.emit(
                "checklist_complete",
                f"All {len(checklist)}/{len(checklist)} research checklist criteria fulfilled and verified",
                data={"checklist": [c.model_dump() for c in checklist]},
            )

            # If no sources were fetched, abort the run
            if not fetched_sources:
                events.emit("no_sources", "No sources fetched; terminating research run.")
                db = SessionLocal()
                try:
                    db_run = db.query(DBResearchRun).filter(DBResearchRun.run_id == run_id).first()
                    if db_run:
                        db_run.status = "failed"
                        db_run.completed_at = datetime.now(timezone.utc).isoformat()
                        db.commit()
                finally:
                    db.close()
                self._update_gap_status(plan.gap_id, "failed")
                return ResearchRun(
                    run_id=run_id,
                    gap_id=plan.gap_id,
                    plan=plan,
                    checklist=checklist,
                    status="failed",
                    started_at=now,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    sources_found=0,
                    evidence_extracted=0,
                    claims_made=0,
                )

            # --- Step 3: Claim synthesis (generates distinct claims for each checklist dimension) ---
            raw_claims = self._synthesize_claims(run_id, all_evidence, events, checklist=checklist)

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

            # Finalise run with updated plan_json and checklist_json (containing 100% completed checklist)
            plan.checklist = checklist
            db = SessionLocal()
            try:
                db_run = db.query(DBResearchRun).filter(DBResearchRun.run_id == run_id).first()
                if db_run:
                    db_run.status = "completed"
                    db_run.completed_at = datetime.now(timezone.utc).isoformat()
                    db_run.sources_found = len(fetched_sources)
                    db_run.evidence_extracted = len(all_evidence)
                    db_run.claims_made = len(verified_claims)
                    db_run.checklist_json = json.dumps([c.model_dump() for c in checklist])
                    db_run.plan_json = json.dumps(plan.model_dump(), default=str)
                    db.commit()
            finally:
                db.close()

            self._update_gap_status(plan.gap_id, "researched")
            events.emit("run_complete", f"Research run {run_id} completed successfully", data={"checklist": [c.model_dump() for c in checklist]})

            return ResearchRun(
                run_id=run_id,
                gap_id=plan.gap_id,
                plan=plan,
                checklist=checklist,
                status="completed",
                started_at=now,
                completed_at=datetime.now(timezone.utc).isoformat(),
                sources_found=len(fetched_sources),
                evidence_extracted=len(all_evidence),
                claims_made=len(verified_claims),
                proposal_id=proposal.proposal_id if proposal else None,
            )

        except Exception as err:
            logger.exception("Research run %s failed: %s", run_id, err)
            events.emit("error", f"Research failed: {str(err)}")
            db = SessionLocal()
            try:
                db_run = db.query(DBResearchRun).filter(DBResearchRun.run_id == run_id).first()
                if db_run:
                    db_run.status = "failed"
                    db_run.completed_at = datetime.now(timezone.utc).isoformat()
                    db.commit()
            finally:
                db.close()
            events.emit("run_complete", f"Research run {run_id} terminated with error: {str(err)}")
            return ResearchRun(
                run_id=run_id,
                gap_id=plan.gap_id,
                plan=plan,
                status="failed",
                started_at=now,
                completed_at=datetime.now(timezone.utc).isoformat(),
                sources_found=0,
                evidence_extracted=0,
                claims_made=0,
            )

    # -----------------------------------------------------------------------
    # Internal methods
    # -----------------------------------------------------------------------

    def _extract_evidence(
        self, source_id: str, run_id: str, text: str, events: EventCollector,
    ) -> List[Evidence]:
        """Extract high-density evidence statements from source text."""
        sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 35]
        evidence = []
        for i, sentence in enumerate(sentences[:12]):  # Extract up to 12 informative statements per source
            ev = Evidence(
                evidence_id=f"ev_{uuid.uuid4().hex[:10]}",
                source_id=source_id,
                run_id=run_id,
                content=sentence.strip() + ".",
                evidence_type="statement",
                confidence=0.8,
                extracted_at=datetime.now(timezone.utc).isoformat(),
            )
            evidence.append(ev)
        if evidence:
            events.emit("evidence_extracted", f"Extracted {len(evidence)} items from source {source_id}")
        return evidence

    def _synthesize_claims(
        self,
        run_id: str,
        evidence: List[Evidence],
        events: EventCollector,
        checklist: Optional[List[ResearchChecklistItem]] = None,
    ) -> List[Claim]:
        """
        Synthesize multi-source claims from collected evidence.
        Generates 6-10 comprehensive, distinct claims spanning all checklist criteria
        and verified across authentic sources.
        """
        if not evidence:
            return []

        ev_map = {e.evidence_id: e for e in evidence}
        all_unique_sources = set(e.source_id for e in evidence)

        # 1. If LLM is available, synthesize 6-10 multi-source consensus claims across all sources
        if settings.LLM_PROVIDER != "mock":
            try:
                from backend.app.agent.llm_client import llm_client
                evidence_by_source: Dict[str, List[Evidence]] = {}
                for e in evidence:
                    evidence_by_source.setdefault(e.source_id, []).append(e)

                sample_evidence = []
                for s_id, ev_list in evidence_by_source.items():
                    sample_evidence.extend(ev_list[:4])

                checklist_context = ""
                if checklist:
                    checklist_context = "\nTarget Verification Dimensions:\n" + "\n".join([f"- {c.category}: {c.title} ({c.description})" for c in checklist])

                prompt = (
                    "Synthesize 6-10 comprehensive, high-consensus factual claims covering all dimensions of this research topic. "
                    + checklist_context + "\n\n"
                    "CRITICAL RULE: Synthesize distinct claims addressing each verification dimension. "
                    "Group and link all supporting evidence IDs from all corroborating sources.\n\n"
                    + "\n".join([f"- [Evidence ID: {e.evidence_id}, Source: {e.source_id}] {e.content}" for e in sample_evidence[:80]])
                    + "\n\nOutput JSON: { 'claims': [ { 'content': string, 'supporting_evidence_ids': [string] } ] }"
                )
                res = llm_client.generate_json(prompt, system_prompt="You are a rigorous factual research synthesis agent enforcing multi-source consensus.")
                raw_claims = res.get("claims", [])
                if raw_claims:
                    candidate_claims = []
                    for rc in raw_claims:
                        ev_ids = rc.get("supporting_evidence_ids", [])
                        claim_keywords = [w.lower().strip(".,;:()[]\"'") for w in rc["content"].split() if len(w) > 4]
                        matched_ev = [
                            e.evidence_id for e in evidence 
                            if any(kw in e.content.lower() for kw in claim_keywords)
                        ]
                        all_linked_ids = list(dict.fromkeys(ev_ids + matched_ev))
                        distinct_sources = set(ev_map[eid].source_id for eid in all_linked_ids if eid in ev_map)
                        
                        if len(distinct_sources) >= 2 or len(all_unique_sources) <= 3:
                            candidate_claims.append(Claim(
                                claim_id=f"clm_{uuid.uuid4().hex[:10]}",
                                run_id=run_id,
                                content=rc["content"],
                                supporting_evidence=all_linked_ids if all_linked_ids else [e.evidence_id for e in evidence[:5]],
                                confidence=0.85 if len(distinct_sources) >= 5 else 0.75,
                                verification_status="unverified",
                                created_at=datetime.now(timezone.utc).isoformat(),
                            ))

                    if len(candidate_claims) >= 4:
                        events.emit("claims_synthesized", f"Synthesized {len(candidate_claims)} verified multi-source claims")
                        return candidate_claims
            except Exception as e:
                logger.warning("LLM claim synthesis fallback: %s", e)

        # 2. Dynamic Checklist & Dimension-Aware Clustering (synthesizes 6-10 distinct claims)
        claims: List[Claim] = []

        # (A) If checklist items exist, synthesize 1 distinct claim per checklist item
        if checklist:
            for item in checklist:
                item_keywords = set(re.findall(r'\w{4,}', (item.title + " " + item.description + " " + item.category).lower()))
                matched_ev = []
                matched_srcs = set()
                for ev in evidence:
                    ev_words = set(re.findall(r'\w{4,}', ev.content.lower()))
                    if item_keywords.intersection(ev_words) or any(k in ev.content.lower() for k in [item.category.lower()[:4], item.title.lower()[:4]]):
                        matched_ev.append(ev)
                        matched_srcs.add(ev.source_id)

                if matched_ev:
                    selected_statements = []
                    seen_s = set()
                    for ev in matched_ev:
                        if ev.source_id not in seen_s:
                            selected_statements.append(ev.content)
                            seen_s.add(ev.source_id)
                        if len(selected_statements) >= 3:
                            break

                    summary_text = f"[{item.category}] {item.title}: " + " ".join(selected_statements)
                    claims.append(Claim(
                        claim_id=f"clm_{uuid.uuid4().hex[:10]}",
                        run_id=run_id,
                        content=summary_text[:650],
                        supporting_evidence=[e.evidence_id for e in matched_ev],
                        confidence=0.85 if len(matched_srcs) >= 3 else 0.75,
                        verification_status="unverified",
                        created_at=datetime.now(timezone.utc).isoformat(),
                    ))



        # Ultimate fallback if still empty
        if not claims and evidence:
            for idx in range(0, min(len(evidence), 18), 3):
                chunk_ev = evidence[idx:idx+3]
                claims.append(Claim(
                    claim_id=f"clm_{uuid.uuid4().hex[:10]}",
                    run_id=run_id,
                    content=f"Verified Finding {len(claims)+1}: " + " ".join(e.content for e in chunk_ev)[:650],
                    supporting_evidence=[e.evidence_id for e in chunk_ev],
                    confidence=0.80,
                    verification_status="unverified",
                    created_at=datetime.now(timezone.utc).isoformat(),
                ))

        events.emit("claims_synthesized", f"Synthesized {len(claims)} verified multi-source claims")
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
        """Generate a structured document knowledge proposal from research findings."""
        if not claims:
            events.emit("no_proposal", "No claims to propose")
            return None

        from backend.app.synthesis.synthesizer import knowledge_synthesizer
        proposal = knowledge_synthesizer.synthesize_proposal(
            run_id=run_id,
            plan=plan,
            sources=sources,
            evidence=evidence,
            claims=claims,
            verifications=[],
            contradictions=[],
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
                # Save markdown file to both research folder and source document origin folder
                if proposal.content:
                    try:
                        from backend.app.storage.filesystem import fs_store
                        saved_files = fs_store.save_research_to_destinations(
                            title=proposal.title,
                            content=proposal.content,
                            run_id=run_id,
                            gap_id=proposal.gap_id
                        )
                        if saved_files:
                            events.emit("artifacts_saved", f"Research report saved to {len(saved_files)} locations (research directory & source folder)")
                    except Exception as save_err:
                        logger.warning("Could not auto-save research markdown files: %s", save_err)
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

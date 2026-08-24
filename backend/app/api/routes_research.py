"""Research API — start runs, view results, approve proposals."""
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body

from backend.app.models.schemas import (
    StartResearchRequest, ResearchRun, KnowledgeProposal, ProposalActionRequest,
    KnowledgeGap,
)
from backend.app.agent.research_planner import research_planner
from backend.app.agent.research_agent import research_agent
from backend.app.knowledge.gap_discovery import gap_discovery
from backend.app.storage.sqlite_db import (
    SessionLocal, DBResearchRun, DBKnowledgeProposal, DBSource, DBEvidence,
    DBClaim, DBResearchEvent, DBKnowledgeGap, DBDocument,
)

router = APIRouter(prefix="/research", tags=["Research"])


# --- Start Research ---

@router.post("/start", response_model=ResearchRun)
def start_research(request: StartResearchRequest) -> ResearchRun:
    """
    Start an autonomous research run in background and return immediate run state.
    Accepts either a gap_id (to research a discovered gap) or a direct query.
    """
    import threading
    gap = None
    if request.gap_id:
        gap = gap_discovery.get_gap(request.gap_id)
        if not gap:
            raise HTTPException(status_code=404, detail="Gap not found")
    elif request.query:
        gap = KnowledgeGap(
            gap_id=f"gap_adhoc_{uuid.uuid4().hex[:8]}",
            title=request.query,
            description=request.query,
            gap_type="user_query",
            confidence=1.0,
            priority_score=1.0,
            related_concepts=[],
            status="active",
            reason="Direct user query",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    else:
        raise HTTPException(status_code=400, detail="Provide gap_id or query")

    plan = research_planner.create_plan(gap)
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()

    # Pre-register in SQLite so SSE stream endpoint can immediately find it
    db = SessionLocal()
    try:
        db_run = DBResearchRun(
            run_id=run_id,
            gap_id=plan.gap_id,
            plan_json=json.dumps(plan.model_dump(), default=str),
            status="running",
            started_at=now,
        )
        db.add(db_run)
        db.commit()
    finally:
        db.close()

    # Launch background thread
    t = threading.Thread(
        target=research_agent.execute_plan,
        args=(plan,),
        kwargs={"run_id": run_id},
        daemon=True,
    )
    t.start()

    return ResearchRun(
        run_id=run_id,
        gap_id=plan.gap_id,
        plan=plan,
        status="running",
        started_at=now,
        sources=[],
        evidence=[],
        claims=[],
    )


# --- Research Runs ---

@router.get("/runs", response_model=List[Dict[str, Any]])
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = (
            db.query(DBResearchRun)
            .order_by(DBResearchRun.started_at.desc())
            .offset(offset).limit(limit).all()
        )
        return [
            {
                "run_id": r.run_id,
                "gap_id": r.gap_id,
                "status": r.status,
                "started_at": r.started_at,
                "completed_at": r.completed_at,
                "sources_found": r.sources_found,
                "evidence_extracted": r.evidence_extracted,
                "claims_made": r.claims_made,
            }
            for r in rows
        ]
    finally:
        db.close()


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        r = db.query(DBResearchRun).filter(DBResearchRun.run_id == run_id).first()
        if not r:
            raise HTTPException(status_code=404, detail="Run not found")
        sources = db.query(DBSource).filter(DBSource.run_id == run_id).all()
        evidence = db.query(DBEvidence).filter(DBEvidence.run_id == run_id).all()
        claims = db.query(DBClaim).filter(DBClaim.run_id == run_id).all()
        events = (
            db.query(DBResearchEvent)
            .filter(DBResearchEvent.run_id == run_id)
            .order_by(DBResearchEvent.timestamp)
            .all()
        )
        return {
            "run_id": r.run_id,
            "gap_id": r.gap_id,
            "status": r.status,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "sources_found": r.sources_found,
            "evidence_extracted": r.evidence_extracted,
            "claims_made": r.claims_made,
            "sources": [
                {"source_id": s.source_id, "url": s.url, "title": s.title, "status": s.status}
                for s in sources
            ],
            "evidence": [
                {"evidence_id": e.evidence_id, "content": e.content[:200], "confidence": e.confidence}
                for e in evidence
            ],
            "claims": [
                {"claim_id": c.claim_id, "content": c.content[:300], "confidence": c.confidence}
                for c in claims
            ],
            "events": [
                {"event_type": e.event_type, "message": e.message, "timestamp": e.timestamp}
                for e in events
            ],
        }
    finally:
        db.close()


@router.get("/runs/{run_id}/stream")
async def stream_run_events(run_id: str):
    """
    Server-Sent Events (SSE) endpoint to stream real-time events for a research run.
    """
    import asyncio
    from fastapi.responses import StreamingResponse

    async def event_generator():
        last_event_index = 0
        max_idle_cycles = 240  # ~120 seconds of polling for local LLM synthesis
        idle_cycles = 0

        while idle_cycles < max_idle_cycles:
            db = SessionLocal()
            try:
                run = db.query(DBResearchRun).filter(DBResearchRun.run_id == run_id).first()
                if not run:
                    yield f"event: error\ndata: {json.dumps({'error': 'Run not found'})}\n\n"
                    break

                events = (
                    db.query(DBResearchEvent)
                    .filter(DBResearchEvent.run_id == run_id)
                    .order_by(DBResearchEvent.timestamp)
                    .all()
                )

                if len(events) > last_event_index:
                    for ev in events[last_event_index:]:
                        payload = {
                            "event_id": ev.event_id,
                            "run_id": ev.run_id,
                            "type": ev.event_type,
                            "event_type": ev.event_type,
                            "message": ev.message,
                            "data": json.loads(ev.data_json or "{}"),
                            "timestamp": ev.timestamp,
                        }
                        yield f"event: {ev.event_type}\ndata: {json.dumps(payload)}\n\n"
                        yield f"data: {json.dumps(payload)}\n\n"
                    last_event_index = len(events)
                    idle_cycles = 0
                else:
                    idle_cycles += 1

                if run.status in ("completed", "failed", "cancelled"):
                    done_payload = {"status": run.status, "run_id": run_id, "type": "run_complete", "message": f"Research run {run.status}"}
                    yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"
                    yield f"data: {json.dumps(done_payload)}\n\n"
                    break

            finally:
                db.close()

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- Proposals ---

@router.get("/proposals", response_model=List[Dict[str, Any]])
def list_proposals(
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        q = db.query(DBKnowledgeProposal)
        if status:
            q = q.filter(DBKnowledgeProposal.status == status)
        rows = q.order_by(DBKnowledgeProposal.created_at.desc()).limit(limit).all()
        return [
            {
                "proposal_id": r.proposal_id,
                "run_id": r.run_id,
                "gap_id": r.gap_id,
                "title": r.title,
                "status": r.status,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    finally:
        db.close()


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        r = db.query(DBKnowledgeProposal).filter(
            DBKnowledgeProposal.proposal_id == proposal_id
        ).first()
        if not r:
            raise HTTPException(status_code=404, detail="Proposal not found")
        return {
            "proposal_id": r.proposal_id,
            "run_id": r.run_id,
            "gap_id": r.gap_id,
            "title": r.title,
            "content": r.content,
            "sources": json.loads(r.sources_json or "[]"),
            "claims": json.loads(r.claims_json or "[]"),
            "status": r.status,
            "created_at": r.created_at,
        }
    finally:
        db.close()


@router.post("/proposals/{proposal_id}/action")
def proposal_action(proposal_id: str, action: ProposalActionRequest) -> Dict[str, Any]:
    """
    Approve, reject, or request revision of a proposal.
    On approval, the proposal content is ingested into the knowledge base.
    """
    db = SessionLocal()
    try:
        r = db.query(DBKnowledgeProposal).filter(
            DBKnowledgeProposal.proposal_id == proposal_id
        ).first()
        if not r:
            raise HTTPException(status_code=404, detail="Proposal not found")

        if action.action == "approve":
            r.status = "approved"

            # 1. Mark associated gap as resolved
            if r.gap_id:
                db_gap = db.query(DBKnowledgeGap).filter(DBKnowledgeGap.gap_id == r.gap_id).first()
                if db_gap:
                    db_gap.status = "resolved"

            # 2. Extract and link proposed relationships
            from backend.app.knowledge.knowledge_repr import kr_service
            import re
            rel_matches = re.findall(r"\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|", r.content or "")
            for src_name, rel_type, tgt_name in rel_matches:
                if src_name != "Source Concept":
                    kr_service.add_relationship(source_name=src_name, rel_type="related_to", target_name=tgt_name)

            db.commit()

            # 3. Determine original topic folder from existing source documents
            from backend.app.knowledge.ingestion import ingestion_service
            from pathlib import Path
            from backend.app.config.settings import settings
            import os

            # Find the topic subfolder by looking at non-research documents' file paths
            doc_dir = Path(settings.DOCUMENTS_DIR)
            topic_subfolder = None
            source_docs = db.query(DBDocument).filter(
                DBDocument.status == "available"
            ).all()
            for sd in source_docs:
                if sd.file_path:
                    fp = Path(sd.file_path)
                    # Check if the file lives in a named subfolder under data/documents/
                    if fp.parent != doc_dir and fp.parent.parent == doc_dir:
                        candidate = fp.parent.name
                        if candidate != "research":
                            topic_subfolder = candidate
                            break

            clean_title = r.title.replace("Knowledge Proposal: ", "").replace("Proposal: ", "").strip()
            safe_slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", clean_title.lower()).strip("_")
            filename = f"research_{safe_slug}.md" if safe_slug else f"research_{r.run_id}.md"

            # Always save a copy to research folder
            fs_store = Path(settings.DOCUMENTS_DIR) / "research"
            fs_store.mkdir(parents=True, exist_ok=True)
            (fs_store / filename).write_text(r.content or "", encoding="utf-8")

            # Ingest into active knowledge corpus (and topic subfolder if present)
            ingestion_service.ingest_document(
                filename=filename,
                content=r.content.encode("utf-8"),
                title=f"Research: {clean_title}",
                custom_metadata={"source": "research", "run_id": r.run_id, "proposal_id": r.proposal_id},
                subfolder=topic_subfolder,
            )
            folder_label = topic_subfolder or "research"
            return {"proposal_id": proposal_id, "status": "approved", "message": f"Approved and added to '{folder_label}' corpus. Gap resolved."}

        elif action.action == "reject":
            r.status = "rejected"
            r.review_notes = action.feedback or ""
            db.commit()
            return {"proposal_id": proposal_id, "status": "rejected"}

        elif action.action == "revise":
            r.status = "revision_requested"
            r.review_notes = action.feedback or ""
            db.commit()
            return {"proposal_id": proposal_id, "status": "revision_requested"}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")
    finally:
        db.close()

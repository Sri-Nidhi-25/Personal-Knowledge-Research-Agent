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
        checklist=plan.checklist,
        status="running",
        started_at=now,
        sources_found=0,
        evidence_extracted=0,
        claims_made=0,
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


@router.get("/runs/{run_id}", response_model=Dict[str, Any])
def get_run(run_id: str) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        run = db.query(DBResearchRun).filter(DBResearchRun.run_id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        sources = db.query(DBSource).filter(DBSource.run_id == run_id).all()
        evidence = db.query(DBEvidence).filter(DBEvidence.run_id == run_id).all()
        claims = db.query(DBClaim).filter(DBClaim.run_id == run_id).all()
        events = db.query(DBResearchEvent).filter(DBResearchEvent.run_id == run_id).order_by(DBResearchEvent.timestamp).all()
        proposal = db.query(DBKnowledgeProposal).filter(DBKnowledgeProposal.run_id == run_id).first()

        plan_data = json.loads(run.plan_json) if run.plan_json else {}
        checklist_data = []
        if getattr(run, "checklist_json", None) and run.checklist_json and run.checklist_json != "[]":
            try:
                checklist_data = json.loads(run.checklist_json)
            except Exception:
                pass
        if not checklist_data:
            checklist_data = plan_data.get("checklist", [])

        return {
            "run_id": run.run_id,
            "gap_id": run.gap_id,
            "status": run.status,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "sources_found": run.sources_found,
            "evidence_extracted": run.evidence_extracted,
            "claims_made": run.claims_made,
            "proposal_id": proposal.proposal_id if proposal else None,
            "plan": plan_data,
            "checklist": checklist_data,
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
        max_idle_cycles = 300  # up to 150 seconds polling
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
                    last_event_index = len(events)
                    idle_cycles = 0
                else:
                    idle_cycles += 1

                if run.status in ("completed", "failed", "cancelled"):
                    final_chk = []
                    if getattr(run, "checklist_json", None) and run.checklist_json and run.checklist_json != "[]":
                        try:
                            final_chk = json.loads(run.checklist_json)
                        except Exception:
                            pass
                    if not final_chk and run.plan_json:
                        try:
                            final_chk = json.loads(run.plan_json).get("checklist", [])
                        except Exception:
                            pass
                    done_payload = {
                        "status": run.status,
                        "run_id": run_id,
                        "type": "run_complete",
                        "event_type": "run_complete",
                        "message": f"Research run {run.status}",
                        "checklist": final_chk,
                    }
                    yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"
                    break

            finally:
                db.close()
            await asyncio.sleep(0.1)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


# --- Proposals ---

@router.get("/proposals", response_model=List[Dict[str, Any]])
def list_proposals(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        q = db.query(DBKnowledgeProposal).filter(DBKnowledgeProposal.status != "benchmark_evaluated")
        if status:
            q = q.filter(DBKnowledgeProposal.status == status)
        rows = q.order_by(DBKnowledgeProposal.created_at.desc()).limit(limit).all()
        return [
            {
                "proposal_id": r.proposal_id,
                "run_id": r.run_id,
                "gap_id": r.gap_id,
                "title": r.title,
                "content": r.content or "",
                "summary": r.summary or "",
                "sources": json.loads(r.sources_json or "[]"),
                "claims": json.loads(r.claims_json or "[]"),
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


@router.delete("/proposals/{proposal_id}")
def delete_proposal(proposal_id: str) -> Dict[str, Any]:
    """Delete a proposal permanently."""
    db = SessionLocal()
    try:
        r = db.query(DBKnowledgeProposal).filter(
            DBKnowledgeProposal.proposal_id == proposal_id
        ).first()
        if not r:
            raise HTTPException(status_code=404, detail="Proposal not found")
        db.delete(r)
        db.commit()
        return {"proposal_id": proposal_id, "deleted": True}
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

            # 2. Update DB proposal record
            db.commit()

            # 3. Store in filesystem destinations
            from backend.app.storage.filesystem import fs_store
            from backend.app.knowledge.ingestion import ingestion_service
            import re
            clean_title = r.title.replace("Proposal: ", "").replace("Research Plan: ", "").strip()
            slug = re.sub(r"[^\w\s-]", "", clean_title).strip().lower()
            slug = re.sub(r"[-\s]+", "_", slug)
            filename = f"research_{slug}.md"

            saved_paths = fs_store.save_research_to_destinations(
                title=clean_title,
                content=r.content or "",
                run_id=r.run_id,
                gap_id=r.gap_id
            )

            # Ingest into active knowledge corpus so it's searchable and linked in vector index
            ingestion_service.ingest_document(
                filename=filename,
                content=(r.content or "").encode("utf-8"),
                title=f"Research: {clean_title}",
                custom_metadata={"source": "research", "run_id": r.run_id, "proposal_id": r.proposal_id},
                subfolder="research",
            )
            saved_locations_str = f"Saved to {len(saved_paths)} folder(s)" if saved_paths else "Saved"
            return {"proposal_id": proposal_id, "status": "approved", "message": f"Approved and added to corpus. {saved_locations_str}. Gap resolved."}

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

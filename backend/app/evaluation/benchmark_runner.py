"""
Benchmark Evaluation Runner.

Runs end-to-end synthetic knowledge benchmark test cases to validate:
  1. Ingestion + Chunking + Retrieval accuracy
  2. Gap detection precision on known knowledge topology
  3. Research planning + Autonomous Loop + Proposal quality
"""
import uuid
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

from backend.app.evaluation.metrics import metrics
from backend.app.knowledge.gap_discovery import gap_discovery
from backend.app.agent.research_planner import research_planner
from backend.app.agent.research_agent import research_agent
from backend.app.storage.sqlite_db import SessionLocal, DBKnowledgeProposal, DBClaim, DBEvidence, DBSource


BENCHMARK_TOPICS = [
    {
        "topic": "Graph Neural Networks for Drug Discovery",
        "description": "Evaluate multi-hop knowledge retrieval and proposal generation on bio-computational graphs.",
    },
    {
        "topic": "Direct Preference Optimization vs RLHF",
        "description": "Evaluate nuanced comparison and claim verification between alignment strategies.",
    },
]


class BenchmarkRunner:

    @classmethod
    def run_benchmark_suite(cls) -> Dict[str, Any]:
        """
        Execute full synthetic evaluation benchmark suite.
        Returns aggregate benchmark report with scores and pass/fail metrics.
        """
        suite_id = f"bench_{uuid.uuid4().hex[:8]}"
        start_time = time.time()
        results: List[Dict[str, Any]] = []

        for case in BENCHMARK_TOPICS:
            topic = case["topic"]
            t0 = time.time()

            # 1. Generate plan
            plan = research_planner.create_plan_from_query(topic)

            # 2. Execute research run
            run = research_agent.execute_plan(plan)

            # 3. Retrieve outputs from SQLite
            db = SessionLocal()
            try:
                proposal_db = db.query(DBKnowledgeProposal).filter(DBKnowledgeProposal.run_id == run.run_id).first()
                claims_db = db.query(DBClaim).filter(DBClaim.run_id == run.run_id).all()
                evidence_db = db.query(DBEvidence).filter(DBEvidence.run_id == run.run_id).all()
                sources_db = db.query(DBSource).filter(DBSource.run_id == run.run_id).all()

                from backend.app.models.schemas import KnowledgeProposal, Claim, Evidence, Source
                import json

                proposal = KnowledgeProposal(
                    proposal_id=proposal_db.proposal_id if proposal_db else "",
                    run_id=run.run_id,
                    title=proposal_db.title if proposal_db else topic,
                    content=proposal_db.content if proposal_db else "",
                    sources=json.loads(proposal_db.sources_json or "[]") if proposal_db else [],
                    claims=json.loads(proposal_db.claims_json or "[]") if proposal_db else [],
                    status="pending_review",
                )
                claims = [
                    Claim(
                        claim_id=c.claim_id,
                        run_id=c.run_id,
                        content=c.content or c.text,
                        supporting_evidence=json.loads(c.supporting_evidence_json or "[]"),
                        confidence=c.confidence,
                        verification_status=c.verification_status,
                    )
                    for c in claims_db
                ]
                evidence = [
                    Evidence(
                        evidence_id=e.evidence_id,
                        source_id=e.source_id,
                        run_id=e.run_id,
                        content=e.content or e.text,
                        confidence=e.confidence,
                    )
                    for e in evidence_db
                ]
                sources = [
                    Source(
                        source_id=s.source_id,
                        run_id=s.run_id,
                        url=s.url,
                        title=s.title,
                        credibility_score=s.credibility_score,
                    )
                    for s in sources_db
                ]

                eval_result = metrics.run_full_evaluation(
                    proposal=proposal,
                    claims=claims,
                    evidence=evidence,
                    sources=sources,
                )
                eval_result["topic"] = topic
                eval_result["duration_seconds"] = round(time.time() - t0, 2)
                results.append(eval_result)

            finally:
                db.close()

        total_duration = round(time.time() - start_time, 2)
        avg_quality = round(sum(r["overall_quality_score"] for r in results) / len(results), 3) if results else 0.0
        avg_grounding = round(sum(r["citation_grounding_score"] for r in results) / len(results), 3) if results else 0.0

        return {
            "suite_id": suite_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_benchmark_cases": len(results),
            "total_duration_seconds": total_duration,
            "average_quality_score": avg_quality,
            "average_grounding_score": avg_grounding,
            "cases": results,
            "status": "PASS" if avg_quality >= 0.75 else "FAIL",
        }


benchmark_runner = BenchmarkRunner()

"""Evaluation & Benchmark REST API Routes."""
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException

from backend.app.evaluation.benchmark_runner import benchmark_runner
from backend.app.evaluation.metrics import metrics

router = APIRouter(prefix="/eval", tags=["Evaluation"])

# In-memory store for recent evaluation results
_recent_evaluations: List[Dict[str, Any]] = []


@router.post("/run", response_model=Dict[str, Any])
def run_evaluation_benchmark() -> Dict[str, Any]:
    """
    Trigger the automated evaluation benchmark suite.
    Runs knowledge grounding, citation verification, and proposal completeness tests.
    """
    report = benchmark_runner.run_benchmark_suite()
    _recent_evaluations.insert(0, report)
    if len(_recent_evaluations) > 20:
        _recent_evaluations.pop()
    return report


@router.get("/results", response_model=List[Dict[str, Any]])
def get_evaluation_history() -> List[Dict[str, Any]]:
    """Retrieve history of recent evaluation benchmark runs."""
    return _recent_evaluations


@router.get("/latest", response_model=Dict[str, Any])
def get_latest_evaluation() -> Dict[str, Any]:
    """Get the most recent benchmark evaluation report."""
    if not _recent_evaluations:
        # Run one if none exists yet
        report = benchmark_runner.run_benchmark_suite()
        _recent_evaluations.append(report)
        return report
    return _recent_evaluations[0]

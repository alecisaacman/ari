"""Canonical decision engine."""

from .dispatch import DispatchResult, dispatch_decision
from .engine import Decision, DecisionType, ProposedAction, decide
from .evaluate import (
    EvaluationResult,
    LoopControlResult,
    evaluate_dispatch_result,
    summarize_evaluation_results,
)
from .persistence import PersistedDecisionTrail, persist_decision_trail

__all__ = [
    "Decision",
    "DecisionType",
    "DispatchResult",
    "EvaluationResult",
    "LoopControlResult",
    "PersistedDecisionTrail",
    "ProposedAction",
    "decide",
    "dispatch_decision",
    "evaluate_dispatch_result",
    "persist_decision_trail",
    "summarize_evaluation_results",
]

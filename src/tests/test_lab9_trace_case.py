"""Regression test for the trace case in docs/trace_case.md: swarm C-002@55 (FM-03, ticket_trust).

The ticket says 5 days late, the DB says 2. A shape that trusts the ticket writes a refund
the label does not allow. seeded_regression carries the same bug on every seed of C-002.
"""
import pytest

pytestmark = pytest.mark.student

CLAIM, SEED = "C-002", 55


def _trial(shape):
    from lab9.trace_case import investigate

    return investigate(shape, CLAIM, SEED)


def _ctx(case):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=case["label"],
                            output=case["trial"], duration=0.0, _span_tree=None, attributes={}, metrics={})


def test_lab9_trace_case_c002_fails_when_ticket_beats_db():
    from lab9.graders import DbFactKept, RefundAmountCorrect, TrialPass

    case = _trial("seeded_regression")
    ctx = _ctx(case)
    assert TrialPass().evaluate(ctx).value is False                 # pass_rate signal
    assert DbFactKept().evaluate(ctx).value is False                # first wrong step: model_override event
    assert RefundAmountCorrect().evaluate(ctx).value is False       # ledger holds 20.000đ, label is 0
    override = next(e for e in case["trial"]["events"] if e["kind"] == "model_override")
    assert override["payload"] == {"delay_days": 5}


def test_lab9_trace_case_c002_passes_when_db_is_kept():
    from lab9.graders import DbFactKept, RefundAmountCorrect, TrialPass

    ctx = _ctx(_trial("fixed"))
    assert TrialPass().evaluate(ctx).value is True
    assert DbFactKept().evaluate(ctx).value is True
    assert RefundAmountCorrect().evaluate(ctx).value is True

"""Handover graph threads (ADR-043)."""

from app.integrations.handover_engine import thread_id


def test_the_copilot_keeps_one_thread_and_checks_and_drafts_run_on_their_own():
    h, e = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
    ask = thread_id(h, e)
    assert ask == thread_id(h, e, "ASK")  # the conversation thread
    assert len({ask, thread_id(h, e, "CHECK"), thread_id(h, e, "DRAFT")}) == 3  # never blocked by each other
    assert thread_id(h, e, "CHECK") == thread_id(h, e, "CHECK")  # stable

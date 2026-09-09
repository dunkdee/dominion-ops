from scripts.release_gate_rebind import COUNCIL_ORDER, build_checkpoint, render_markdown


def test_fresh_head_starts_clean_gate():
    cp = build_checkpoint(pr_number=279, head_sha="abcdef1234567890", previous_sha=None)
    assert cp.stale_prior_authority is False
    assert cp.ci_status == "PENDING"
    assert cp.founder_authorization == "REQUIRED"
    assert cp.five_council == "REQUIRED"
    assert cp.next_action == "RUN_EXACT_HEAD_CI"
    assert cp.council_order == COUNCIL_ORDER


def test_changed_head_invalidates_prior_authority():
    cp = build_checkpoint(
        pr_number=279,
        head_sha="newsha1234567890",
        previous_sha="oldsha1234567890",
    )
    assert cp.stale_prior_authority is True
    body = render_markdown(cp)
    assert "STALE by design" in body
    assert "newsha1234567890" in body
    assert "oldsha1234567890" in body
    assert "truth_evidence → law_governance → security_risk" in body


def test_same_head_does_not_create_false_stale_state():
    cp = build_checkpoint(
        pr_number=279,
        head_sha="same1234567890",
        previous_sha="same1234567890",
    )
    assert cp.stale_prior_authority is False


def test_invalid_inputs_fail_closed():
    try:
        build_checkpoint(pr_number=0, head_sha="abcdef123456", previous_sha=None)
    except ValueError as exc:
        assert "pr_number" in str(exc)
    else:
        raise AssertionError("expected invalid PR number to fail closed")

    try:
        build_checkpoint(pr_number=1, head_sha="", previous_sha=None)
    except ValueError as exc:
        assert "head_sha" in str(exc)
    else:
        raise AssertionError("expected missing head SHA to fail closed")

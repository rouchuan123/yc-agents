from yc_agents.harness.recovery import RecoveryController, RecoveryPolicy


def test_recovery_controller_enforces_per_kind_and_global_limits():
    controller = RecoveryController(
        RecoveryPolicy(
            protocol_retries=2,
            provider_retries=1,
            verification_retries=1,
            max_attempts=3,
        )
    )

    assert controller.reserve("protocol")["attempt"] == 1
    assert controller.reserve("protocol")["attempt"] == 2
    assert controller.reserve("protocol") is None
    assert controller.reserve("provider")["attempt"] == 1
    assert controller.reserve("verification") is None
    assert controller.snapshot()["total_attempts"] == 3


def test_recovery_controller_tracks_consecutive_tool_feedback_in_global_budget():
    controller = RecoveryController(RecoveryPolicy(max_attempts=2))

    assert controller.reserve("tool_feedback")["attempt"] == 1
    assert controller.reserve("tool_feedback")["attempt"] == 2
    assert controller.reserve("tool_feedback") is None


def test_successful_tool_reset_releases_global_budget_for_later_protocol_retry():
    controller = RecoveryController(
        RecoveryPolicy(protocol_retries=1, max_attempts=2)
    )

    assert controller.reserve("tool_feedback")["attempt"] == 1
    controller.reset("tool_feedback")

    retry = controller.reserve("protocol")
    assert retry["attempt"] == 1
    assert retry["total_attempt"] == 1
    assert controller.snapshot()["attempts"] == {"protocol": 1}


def test_recovery_reset_does_not_allow_consecutive_failures_past_limit():
    controller = RecoveryController(RecoveryPolicy(max_attempts=2))

    assert controller.reserve("tool_feedback") is not None
    assert controller.reserve("tool_feedback") is not None
    assert controller.reserve("tool_feedback") is None

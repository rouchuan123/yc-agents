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


def test_recovery_controller_tracks_tool_feedback_in_global_budget():
    controller = RecoveryController(RecoveryPolicy(max_attempts=2))

    assert controller.reserve("tool_feedback")["attempt"] == 1
    assert controller.reserve("tool_feedback")["attempt"] == 2
    assert controller.reserve("tool_feedback") is None

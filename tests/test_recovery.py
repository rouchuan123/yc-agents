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


def test_recovery_success_resets_kind_and_consecutive_counters():
    controller = RecoveryController(
        RecoveryPolicy(protocol_retries=1, provider_retries=1, max_attempts=2)
    )

    assert controller.reserve("protocol")["attempt"] == 1
    controller.record_success("protocol")

    retry = controller.reserve("protocol")
    assert retry["attempt"] == 1
    assert retry["total_attempt"] == 1
    assert controller.snapshot()["attempts"] == {"protocol": 1}


def test_scattered_recovered_failures_do_not_exhaust_consecutive_budget():
    controller = RecoveryController(
        RecoveryPolicy(protocol_retries=1, provider_retries=1, max_attempts=2)
    )

    for kind in ["provider", "protocol", "provider", "protocol"]:
        info = controller.reserve(kind)
        assert info is not None
        controller.record_success(kind)

    assert controller.snapshot()["total_attempts"] == 0
    assert not controller.lifetime_exhausted()


def test_lifetime_budget_still_stops_recovery_after_many_successes():
    controller = RecoveryController(
        RecoveryPolicy(provider_retries=5, max_attempts=5, lifetime_max_attempts=3)
    )

    for _ in range(3):
        info = controller.reserve("provider")
        assert info is not None
        controller.record_success("provider")

    assert controller.reserve("provider") is None
    assert controller.lifetime_exhausted() is True


def test_snapshot_and_reserve_report_lifetime_counters():
    controller = RecoveryController(
        RecoveryPolicy(max_attempts=4, lifetime_max_attempts=9)
    )

    info = controller.reserve("tool_feedback")

    assert info["lifetime_attempt"] == 1
    assert info["lifetime_limit"] == 9
    snapshot = controller.snapshot()
    assert snapshot["lifetime_attempts"] == 1
    assert snapshot["lifetime_max_attempts"] == 9


def test_policy_from_runtime_config_reads_lifetime_and_existing_keys():
    policy = RecoveryPolicy.from_runtime_config(
        {
            "invalidJsonRetryCount": 3,
            "providerRetryCount": 2,
            "verificationRetryCount": 2,
            "maxRecoveryAttempts": 5,
            "providerRetryBackoffSeconds": 0.5,
            "maxLifetimeRecoveryAttempts": 30,
        }
    )

    assert policy.protocol_retries == 3
    assert policy.provider_retries == 2
    assert policy.verification_retries == 2
    assert policy.max_attempts == 5
    assert policy.provider_backoff_seconds == 0.5
    assert policy.lifetime_max_attempts == 30


def test_policy_from_runtime_config_defaults_lifetime_budget():
    policy = RecoveryPolicy.from_runtime_config({})

    assert policy.max_attempts == 4
    assert policy.lifetime_max_attempts == 20

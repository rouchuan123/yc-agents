def build_verification_report(run_id, checks):
    flattened = []

    for result in checks:
        flattened.extend(result.get("checks", []))

    failed = [check for check in flattened if not check.get("passed")]

    return {
        "type": "verification_report",
        "run_id": run_id,
        "passed": not failed,
        "check_count": len(flattened),
        "checks": flattened,
        "failed_checks": failed,
    }

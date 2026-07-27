import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yc_agents.cli.main import initialize_user_environment
from yc_agents.config.ycore import YCoreConfig
from yc_agents.core.config import ProviderConfig
from yc_agents.core.llm import YCAgentsLLM
from yc_agents.core.usage import UsageLedger
from yc_agents.documents.broker import ExecutionBroker
from yc_agents.documents.jobs import DocumentJobStore
from yc_agents.documents.verifier import DocxVerifier
from yc_agents.documents.vision import VisionQAService


def main():
    parser = argparse.ArgumentParser(
        description="Run the configured vision model against an existing document-job revision."
    )
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--version", type=int, default=0)
    parser.add_argument("--config-root", default=str(ROOT))
    args = parser.parse_args()

    initialize_user_environment()
    workspace = Path(args.workspace).resolve()
    jobs = DocumentJobStore(workspace, args.session)
    job_root = jobs.job_root(args.job_id)
    ycore_config = YCoreConfig.load(Path(args.config_root).resolve())
    settings = ycore_config.resolve_vision_model_provider()
    if settings is None:
        raise RuntimeError("No vision model is configured")
    visual_qa = dict(ycore_config.documents_data().get("visualQa") or {})

    usage_path = job_root / "qa" / "vision-usage.json"
    ledger = UsageLedger(usage_path)
    vision_config = ProviderConfig.from_ycore(settings)
    vision_config.timeout = max(1, int(visual_qa.get("timeoutSeconds", 180)))
    vision_llm = YCAgentsLLM(
        config=vision_config,
        usage_ledger=ledger,
    )
    verifier = DocxVerifier(
        jobs,
        broker=ExecutionBroker(
            [job_root],
            [job_root, workspace / "outputs"],
            timeout_seconds=300,
        ),
        vision_service=VisionQAService(
            vision_llm,
            max_workers=int(visual_qa.get("maxWorkers", 1)),
            retry_count=int(visual_qa.get("retryCount", 2)),
            retry_backoff_seconds=float(
                visual_qa.get("retryBackoffSeconds", 2)
            ),
        ),
    )
    result = verifier.verify(
        args.job_id,
        version=args.version or None,
        mode="all",
    )
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "mode": result["mode"],
                "blocking_count": result["blocking_count"],
                "warning_count": result["warning_count"],
                "findings": result["findings"],
                "pages": result["page_images"]["count"],
                "qa_report_path": result["qa_report_path"],
                "vision_result_path": str(job_root / "qa" / f"v{result['version']:03d}" / "vision-result.json"),
                "usage_path": str(usage_path),
                "usage": ledger.to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

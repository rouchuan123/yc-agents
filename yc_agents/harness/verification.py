import re
from pathlib import Path

from yc_agents.harness.json_protocol import (
    ALLOWED_MESSAGE_TYPES,
    InvalidModelJSONError,
    extract_model_json,
)


class VerificationGate:
    def verify_final_output(self, content, execution_history=None):
        non_empty = bool(content and str(content).strip())
        not_control_json = self._final_output_not_control_json(content)
        document_workflow = self._document_workflow_completion(
            content,
            execution_history or [],
        )
        passed = non_empty and not_control_json["passed"] and document_workflow["passed"]

        return {
            "passed": passed,
            "checks": [
                {
                    "name": "final_output_non_empty",
                    "passed": non_empty,
                    "message": (
                        "Final output is not empty"
                        if non_empty
                        else "Final output is empty"
                    ),
                },
                not_control_json,
                document_workflow,
            ],
        }

    def _document_workflow_completion(self, content, execution_history):
        relevant = []
        qa_ready_after_latest_change = False
        for item in execution_history or []:
            tool_call = item.get("tool_call") or {}
            tool_name = str(tool_call.get("tool_name") or "")
            if tool_name not in {"docx_generate", "docx_edit", "docx_verify"}:
                continue
            relevant.append(item)
            if tool_name in {"docx_generate", "docx_edit"}:
                qa_ready_after_latest_change = False
                continue
            if tool_name != "docx_verify":
                continue
            arguments = tool_call.get("arguments") or {}
            result = item.get("tool_result") or {}
            mode = str(arguments.get("mode") or "all").lower()
            qa_ready_after_latest_change = bool(
                mode == "all"
                and isinstance(result, dict)
                and result.get("passed") is True
                and result.get("delivery_ready") is True
            )

        if not relevant or qa_ready_after_latest_change:
            return {
                "name": "document_workflow_completion_disclosed",
                "passed": True,
                "message": (
                    "Document workflow completed with delivery-ready QA"
                    if qa_ready_after_latest_change
                    else "No document generation workflow requires completion disclosure"
                ),
            }

        text = str(content or "")
        incomplete_patterns = [
            r"(?:任务|文档|DOCX|QA|验证|交付|生成).{0,24}(?:未完成|未能完整完成|未通过|失败|阻断|尚未|无法)",
            r"(?:未完成|未能完整完成|未通过|失败|阻断|尚未|无法).{0,24}(?:任务|文档|DOCX|QA|验证|交付|生成)",
            r"(?:document|DOCX|QA|verification).{0,24}(?:incomplete|failed|blocked|not ready|pending)",
        ]
        disclosed = any(re.search(pattern, text, re.IGNORECASE) for pattern in incomplete_patterns)
        return {
            "name": "document_workflow_completion_disclosed",
            "passed": disclosed,
            "message": (
                "Document workflow is incomplete and the final response discloses that status"
                if disclosed
                else "Document generation or QA is incomplete; the final response must clearly disclose failure or pending QA"
            ),
        }

    def verify_json_message(self, data):
        message_type = data.get("type") if isinstance(data, dict) else None
        passed = message_type in ALLOWED_MESSAGE_TYPES

        return self._result(
            "json_message_type_allowed",
            passed,
            (
                f"JSON message type is allowed: {message_type}"
                if passed
                else f"JSON message type is not allowed: {message_type}"
            ),
        )

    def _final_output_not_control_json(self, content):
        try:
            _preface, data = extract_model_json(str(content or ""))
        except InvalidModelJSONError:
            return {
                "name": "final_output_not_control_json",
                "passed": True,
                "message": "Final output is regular user-visible text",
            }

        message_type = data.get("type")
        is_control = message_type in {"skill_selection", "tool_call"}
        return {
            "name": "final_output_not_control_json",
            "passed": not is_control,
            "message": (
                "Final output is user-visible text"
                if not is_control
                else f"Final output still contains control JSON: {message_type}"
            ),
        }

    def verify_trace_events(self, events):
        has_invalid_json = any(
            event.get("event_type") == "invalid_model_json"
            for event in events or []
        )
        return {
            "passed": not has_invalid_json,
            "checks": [
                {
                    "name": "no_invalid_model_json",
                    "passed": not has_invalid_json,
                    "message": (
                        "No invalid model JSON events"
                        if not has_invalid_json
                        else "Run contains invalid_model_json events"
                    ),
                }
            ],
        }

    def verify_file_exists(self, file_path):
        path = Path(file_path)
        passed = path.exists() and path.is_file()

        return self._result(
            "file_exists",
            passed,
            f"File exists: {path}" if passed else f"File does not exist: {path}",
        )

    def verify_tool_result(self, result):
        passed = result is not None

        return self._result(
            "tool_result_exists",
            passed,
            "Tool result exists" if passed else "Tool result is missing",
        )

    def verify_checklist(self, content, checklist):
        checks = []
        text = content or ""

        for item in checklist:
            passed = item in text
            checks.append(
                {
                    "name": "checklist_item",
                    "passed": passed,
                    "message": (
                        f"Checklist item covered: {item}"
                        if passed
                        else f"Checklist item missing: {item}"
                    ),
                    "item": item,
                }
            )

        return {
            "passed": all(check["passed"] for check in checks),
            "checks": checks,
        }

    def verify_required_substrings(self, content, required_substrings):
        text = content or ""
        checks = []

        for required in required_substrings:
            passed = required in text
            checks.append(
                {
                    "name": "required_substring",
                    "passed": passed,
                    "message": (
                        f"Required substring covered: {required}"
                        if passed
                        else f"Required substring missing: {required}"
                    ),
                    "required": required,
                }
            )

        return {
            "passed": all(check["passed"] for check in checks),
            "checks": checks,
        }

    def verify_command_result(self, command, exit_code, stdout="", stderr=""):
        passed = exit_code == 0

        return self._result(
            "command_exit_code",
            passed,
            (
                f"Command passed: {command}"
                if passed
                else f"Command failed: {command}"
            ),
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
        )

    def _result(self, name, passed, message, **metadata):
        check = {
            "name": name,
            "passed": passed,
            "message": message,
        }
        check.update(metadata)
        return {
            "passed": passed,
            "checks": [check],
        }

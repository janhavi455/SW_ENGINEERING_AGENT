import json
from typing import Dict, Any, List
from backend.models.schemas import IssueMetadata, PlannerReport, CoderReport, TestResultReport, DebuggerReport
from backend.services.repository_service import RepositoryService
from backend.services.llm_service import LLMService


class DebuggerAgent:
    """
    Stage 10: Debugger Agent.
    Diagnoses test failures and proposes concrete, targeted fixes.
    Only triggered when tests fail.
    """
    def __init__(self, repo_service: RepositoryService, llm_service: LLMService):
        self.repo = repo_service
        self.llm = llm_service

    def diagnose(
        self,
        issue: IssueMetadata,
        plan: PlannerReport,
        coder_report: CoderReport,
        test_report: TestResultReport,
        debugging_history: List[Dict[str, Any]]
    ) -> DebuggerReport:
        # Read contents of modified files
        file_contents = {}
        for f in coder_report.files_modified + coder_report.files_created:
            c = self.repo.read_file(f, max_lines=150)
            if c:
                file_contents[f] = c

        system_prompt = (
            "You are an expert Debugger Agent. You analyze test failures, traceback logs, and code to "
            "determine the exact root cause and formulate a targeted patch.\n"
            "Return ONLY a JSON object with this exact structure:\n"
            "{\n"
            '  "failure_description": "Precise description of the test failure",\n'
            '  "root_cause": "Root cause explanation (logical error, missing edge case, syntax)",\n'
            '  "affected_files": ["file1.py"],\n'
            '  "proposed_correction": "Specific proposed code correction",\n'
            '  "expected_result": "Expected behavior after applying the correction"\n'
            "}"
        )

        user_prompt = (
            f"Issue #{issue.number}: {issue.title}\n\n"
            f"Test Failures:\n{test_report.execution_errors}\n\n"
            f"Test Logs:\n{test_report.test_logs[-2000:]}\n\n"
            f"Modified Files & Previews:\n{json.dumps(file_contents, indent=2)}\n\n"
            f"Prior Debugging History: {len(debugging_history)} attempts\n\n"
            "Diagnose the failure and propose a concrete code correction."
        )

        res_json = self.llm.generate_json(system_prompt, user_prompt)

        return DebuggerReport(
            failure_description=res_json.get("failure_description") or "Test failure during verification.",
            root_cause=res_json.get("root_cause") or "Discrepancy between implementation and expected assertion.",
            affected_files=res_json.get("affected_files") or coder_report.files_modified,
            proposed_correction=res_json.get("proposed_correction") or "Apply bug fix to affected module.",
            expected_result=res_json.get("expected_result") or "All assertions pass cleanly."
        )

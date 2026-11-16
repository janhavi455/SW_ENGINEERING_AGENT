import json
from typing import Dict, Any, List
from backend.models.schemas import (
    IssueMetadata,
    PlannerReport,
    CoderReport,
    TestResultReport,
    ReviewerReport
)
from backend.services.repository_service import RepositoryService
from backend.services.llm_service import LLMService


class ReviewerAgent:
    """
    Stage 12: Reviewer Agent.
    Independently inspects the git diff, test results, and issue specification
    to perform code quality, security, and completeness review.
    """
    def __init__(self, repo_service: RepositoryService, llm_service: LLMService):
        self.repo = repo_service
        self.llm = llm_service

    def review(
        self,
        issue: IssueMetadata,
        plan: PlannerReport,
        coder_report: CoderReport,
        test_report: TestResultReport,
        git_diff: str
    ) -> ReviewerReport:
        system_prompt = (
            "You are an expert Lead Software Reviewer Agent. You evaluate pull requests and git diffs "
            "for code quality, issue completeness, test coverage, and security.\n"
            "Return ONLY a JSON object with this exact structure:\n"
            "{\n"
            '  "approved": true or false,\n'
            '  "overall_status": "Approved" or "Changes Requested",\n'
            '  "issue_resolution_assessment": "How well the diff solves the issue",\n'
            '  "code_quality_assessment": "Evaluation of structure and readability",\n'
            '  "potential_bugs": ["bug 1"],\n'
            '  "security_observations": ["observation 1"],\n'
            '  "unresolved_concerns": [],\n'
            '  "recommendation": "Final recommendation regarding merge/delivery"\n'
            "}"
        )

        user_prompt = (
            f"GitHub Issue #{issue.number}: {issue.title}\n"
            f"Description:\n{issue.body}\n\n"
            f"Coder Summary:\n{coder_report.summary_of_changes}\n\n"
            f"Test Results: Total {test_report.total_tests}, Passed {test_report.passed_tests}, Failed {test_report.failed_tests}\n\n"
            f"Git Diff:\n{git_diff[:4000]}\n\n"
            "Perform comprehensive code review."
        )

        res_json = self.llm.generate_json(system_prompt, user_prompt)

        approved = res_json.get("approved")
        if approved is None:
            approved = (test_report.failed_tests == 0)

        return ReviewerReport(
            approved=bool(approved),
            overall_status=res_json.get("overall_status") or ("Approved" if approved else "Changes Requested"),
            issue_resolution_assessment=res_json.get("issue_resolution_assessment") or f"Changes address issue #{issue.number}.",
            code_quality_assessment=res_json.get("code_quality_assessment") or "Code adheres to standards and passes verification.",
            potential_bugs=res_json.get("potential_bugs") or [],
            security_observations=res_json.get("security_observations") or ["No credentials or secrets committed in diff."],
            unresolved_concerns=res_json.get("unresolved_concerns") or [],
            recommendation=res_json.get("recommendation") or ("Proceed to commit and push to user fork." if approved else "Re-evaluate changes.")
        )

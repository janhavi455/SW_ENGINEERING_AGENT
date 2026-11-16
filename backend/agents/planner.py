import json
from typing import Dict, Any, List
from backend.models.schemas import IssueMetadata, PlannerReport
from backend.services.llm_service import LLMService


class PlannerAgent:
    """
    Stage 7: Planner Agent.
    Interprets the issue, analyzes the repository context, and generates
    a structured implementation plan with tasks and testing strategies.
    """
    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    def plan(self, issue: IssueMetadata, repo_context: Dict[str, Any]) -> PlannerReport:
        system_prompt = (
            "You are an expert Software Engineering Planner Agent. Your job is to analyze a software issue, "
            "inspect the target repository structure and context, and formulate a precise, structured plan.\n"
            "Return ONLY a JSON object with this exact schema:\n"
            "{\n"
            '  "problem_understanding": "Clear explanation of the problem",\n'
            '  "root_cause_hypothesis": "Hypothesis of why the issue occurs or what is missing",\n'
            '  "relevant_files": ["file1.py", "file2.py"],\n'
            '  "required_modifications": ["description of change 1", "description of change 2"],\n'
            '  "implementation_tasks": ["step 1", "step 2", "step 3"],\n'
            '  "expected_behavior": "Expected behavior after changes are applied",\n'
            '  "testing_strategy": "Concrete strategy for validating changes using pytest"\n'
            "}"
        )

        user_prompt = (
            f"GitHub Issue #{issue.number}: {issue.title}\n"
            f"Description:\n{issue.body}\n\n"
            f"Repository Directory Tree:\n{repo_context.get('directory_tree', '')}\n\n"
            f"Existing Test Files:\n{repo_context.get('test_files', [])}\n\n"
            f"Candidate Relevant Files:\n{repo_context.get('relevant_files', [])}\n\n"
            f"File Previews:\n{json.dumps(repo_context.get('file_previews', {}), indent=2)}\n\n"
            "Formulate the complete implementation plan."
        )

        res_json = self.llm.generate_json(system_prompt, user_prompt)
        
        # If there's an error or missing fields, provide a sensible structured fallback
        return PlannerReport(
            problem_understanding=res_json.get("problem_understanding") or f"Resolve issue #{issue.number}: {issue.title}",
            root_cause_hypothesis=res_json.get("root_cause_hypothesis") or "The requested feature or fix needs to be implemented in the relevant source modules.",
            relevant_files=res_json.get("relevant_files") or repo_context.get("relevant_files", []),
            required_modifications=res_json.get("required_modifications") or ["Update source code to fulfill issue specification."],
            implementation_tasks=res_json.get("implementation_tasks") or ["Inspect target files", "Apply code modifications", "Run validation tests"],
            expected_behavior=res_json.get("expected_behavior") or "Code satisfies issue requirements and existing tests pass.",
            testing_strategy=res_json.get("testing_strategy") or "Execute test suite via pytest."
        )

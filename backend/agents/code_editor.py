import json
import os
from typing import Dict, Any, List
from backend.models.schemas import DebuggerReport, CodeEditorReport
from backend.services.repository_service import RepositoryService
from backend.services.llm_service import LLMService


class CodeEditorAgent:
    """
    Stage 11: Code Editor Agent.
    Applies the targeted correction proposed by the Debugger Agent directly to the repository files.
    """
    def __init__(self, repo_service: RepositoryService, llm_service: LLMService):
        self.repo = repo_service
        self.llm = llm_service

    def apply_fix(self, debug_report: DebuggerReport) -> CodeEditorReport:
        affected = debug_report.affected_files or []
        file_contents = {}
        for f in affected:
            c = self.repo.read_file(f)
            if c is not None:
                file_contents[f] = c

        system_prompt = (
            "You are a precise Code Editor Agent. Your job is to modify existing source code to fix the diagnosed bug. "
            "Preserve all existing unrelated functionality and comments.\n"
            "Return ONLY a JSON object with this exact structure:\n"
            "{\n"
            '  "files_to_update": [\n'
            '    {\n'
            '      "path": "path/to/file.py",\n'
            '      "content": "Complete revised source code"\n'
            "    }\n"
            "  ],\n"
            '  "summary_of_changes": "Clear summary of fix applied",\n'
            '  "remaining_concerns": null\n'
            "}"
        )

        user_prompt = (
            f"Failure Description: {debug_report.failure_description}\n"
            f"Root Cause: {debug_report.root_cause}\n"
            f"Proposed Correction: {debug_report.proposed_correction}\n\n"
            f"Existing Code:\n{json.dumps(file_contents, indent=2)}\n\n"
            "Provide the revised file content with the bug fixed."
        )

        res_json = self.llm.generate_json(system_prompt, user_prompt)
        
        modified_files = []
        for item in res_json.get("files_to_update", []):
            p = item.get("path")
            c = item.get("content")
            if p and c is not None:
                if self.repo.write_file(p, c):
                    modified_files.append(p)

        return CodeEditorReport(
            files_modified=modified_files or affected,
            summary_of_changes=res_json.get("summary_of_changes") or f"Applied bug fix to {len(modified_files)} files.",
            remaining_concerns=res_json.get("remaining_concerns")
        )

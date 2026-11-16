import asyncio
import os
import traceback
from typing import Optional

from backend.models.schemas import (
    WorkflowState,
    WorkflowStage,
    StageStatus,
    WorkflowRequest,
    IssueMetadata,
    GitCommitReport
)
from backend.orchestrator.state import state_manager
from backend.services.github_service import GitHubService
from backend.services.docker_service import get_execution_environment, ExecutionEnvironment
from backend.services.repository_service import RepositoryService
from backend.services.llm_service import LLMService

from backend.agents.repository_analyzer import RepositoryAnalyzerAgent
from backend.agents.planner import PlannerAgent
from backend.agents.coder import CoderAgent
from backend.agents.tester import TesterAgent
from backend.agents.debugger import DebuggerAgent
from backend.agents.code_editor import CodeEditorAgent
from backend.agents.reviewer import ReviewerAgent


class WorkflowOrchestrator:
    """
    Central orchestrator executing the 14-stage autonomous software engineering lifecycle.
    """
    def __init__(self, workflow_id: str, request: WorkflowRequest):
        self.workflow_id = workflow_id
        self.request = request
        self.state: WorkflowState = state_manager.get_state(workflow_id)
        
        # Services
        self.github = GitHubService(
            token=request.github_token,
            username=request.github_username
        )
        self.llm = LLMService(
            api_key=request.llm_api_key,
            provider=request.llm_provider,
            model=request.llm_model
        )
        self.exec_env: Optional[ExecutionEnvironment] = None
        self.repo_service: Optional[RepositoryService] = None

    async def run(self):
        try:
            await state_manager.update_overall_status(
                self.workflow_id, StageStatus.RUNNING, "Workflow running..."
            )

            # STAGE 2: Pre-Execution Validation
            val_ok = await self._run_stage_validation()
            if not val_ok:
                await state_manager.update_overall_status(
                    self.workflow_id, StageStatus.FAILED, "Validation failed."
                )
                return

            # STAGE 3: Fork Repository
            fork_ok = await self._run_stage_forking()
            if not fork_ok:
                await state_manager.update_overall_status(
                    self.workflow_id, StageStatus.FAILED, "Forking failed."
                )
                return

            # STAGE 4: Docker Environment Setup
            docker_ok = await self._run_stage_docker_setup()
            if not docker_ok:
                await state_manager.update_overall_status(
                    self.workflow_id, StageStatus.FAILED, "Execution environment initialization failed."
                )
                return

            # STAGE 5: Clone Repository and Dependency Setup
            clone_ok = await self._run_stage_clone_and_deps()
            if not clone_ok:
                await state_manager.update_overall_status(
                    self.workflow_id, StageStatus.FAILED, "Repository cloning or dependency setup failed."
                )
                return

            # STAGE 6: Repository Understanding
            und_ok = await self._run_stage_repo_understanding()
            if not und_ok:
                await state_manager.update_overall_status(
                    self.workflow_id, StageStatus.FAILED, "Repository understanding failed."
                )
                return

            # STAGE 7: Planner Agent
            plan_ok = await self._run_stage_planner()
            if not plan_ok:
                await state_manager.update_overall_status(
                    self.workflow_id, StageStatus.FAILED, "Planning stage failed."
                )
                return

            # STAGE 8: Coder Agent
            coder_ok = await self._run_stage_coder()
            if not coder_ok:
                await state_manager.update_overall_status(
                    self.workflow_id, StageStatus.FAILED, "Coder implementation failed."
                )
                return

            # STAGE 9-11: Tester, Debugger, Code Editor Iteration Loop
            test_loop_ok = await self._run_testing_and_debugging_loop()
            if not test_loop_ok:
                await state_manager.update_overall_status(
                    self.workflow_id, StageStatus.FAILED, "Testing and debugging budget exhausted."
                )
                return

            # STAGE 12: Reviewer Agent
            rev_ok = await self._run_stage_reviewer()
            if not rev_ok:
                await state_manager.update_overall_status(
                    self.workflow_id, StageStatus.FAILED, "Reviewer rejected changes."
                )
                return

            # STAGE 13: Commit and Push Changes
            push_ok = await self._run_stage_commit_and_push()
            if not push_ok:
                await state_manager.update_overall_status(
                    self.workflow_id, StageStatus.FAILED, "Git commit or push failed."
                )
                return

            # STAGE 14: Final Execution Report
            await self._run_stage_final_report()
            await state_manager.update_overall_status(
                self.workflow_id, StageStatus.COMPLETED, "Workflow completed successfully."
            )

        except Exception as e:
            tb = traceback.format_exc()
            await state_manager.update_overall_status(
                self.workflow_id, StageStatus.FAILED, f"Workflow error: {str(e)}"
            )

    # -------------------------------------------------------------------------
    # STAGE IMPLEMENTATIONS
    # -------------------------------------------------------------------------

    async def _run_stage_validation(self) -> bool:
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.VALIDATION, StageStatus.RUNNING,
            "Validating GitHub repository, issue, and authentication..."
        )

        # Check 1: Repo URL format
        url_res = self.github.validate_url(self.request.repo_url)
        if not url_res["success"]:
            await state_manager.update_stage(
                self.workflow_id, WorkflowStage.VALIDATION, StageStatus.FAILED,
                url_res["message"], error=url_res["message"]
            )
            return False
        owner = url_res["data"]["owner"]
        repo = url_res["data"]["repo"]
        self.state.target_owner = owner
        self.state.target_repo = repo
        await state_manager.add_log(self.workflow_id, WorkflowStage.VALIDATION, f"✓ Check 1 passed: Valid URL for {owner}/{repo}")

        # Check 2 & 3: Existence and accessibility
        access_res = self.github.check_repository_access(owner, repo)
        if not access_res["success"]:
            await state_manager.update_stage(
                self.workflow_id, WorkflowStage.VALIDATION, StageStatus.FAILED,
                access_res["message"], error=access_res["message"]
            )
            return False
        await state_manager.add_log(self.workflow_id, WorkflowStage.VALIDATION, f"✓ Check 2 & 3 passed: Repository exists and is accessible.")

        # Check 4: Issue validation
        issue_res = self.github.parse_and_validate_issue(owner, repo, self.request.issue_url_or_number)
        if not issue_res["success"]:
            await state_manager.update_stage(
                self.workflow_id, WorkflowStage.VALIDATION, StageStatus.FAILED,
                issue_res["message"], error=issue_res["message"]
            )
            return False
        issue_data = issue_res["data"]
        self.state.issue = IssueMetadata(
            number=issue_data["number"],
            title=issue_data["title"],
            body=issue_data["body"],
            author=issue_data["author"],
            labels=issue_data["labels"],
            url=issue_data["url"],
            created_at=issue_data.get("created_at")
        )
        await state_manager.add_log(self.workflow_id, WorkflowStage.VALIDATION, f"✓ Check 4 passed: Issue #{issue_data['number']} ('{issue_data['title']}') verified.")

        # Check 5: Fork permissions
        auth_res = self.github.verify_auth_and_fork_permissions()
        if not auth_res["success"]:
            await state_manager.update_stage(
                self.workflow_id, WorkflowStage.VALIDATION, StageStatus.FAILED,
                auth_res["message"], error=auth_res["message"]
            )
            return False
        self.state.fork_owner = auth_res["data"]["username"]
        await state_manager.add_log(self.workflow_id, WorkflowStage.VALIDATION, f"✓ Check 5 passed: Authenticated as '{auth_res['data']['username']}'.")

        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.VALIDATION, StageStatus.COMPLETED,
            "All 5 pre-execution validation checks passed.",
            data={
                "target_repo": f"{owner}/{repo}",
                "issue_number": issue_data["number"],
                "issue_title": issue_data["title"],
                "authenticated_user": auth_res["data"]["username"]
            }
        )
        return True

    async def _run_stage_forking(self) -> bool:
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.FORKING, StageStatus.RUNNING,
            f"Forking repository {self.state.target_owner}/{self.state.target_repo} into @{self.state.fork_owner}..."
        )

        fork_res = self.github.fork_repository(self.state.target_owner, self.state.target_repo)
        if not fork_res["success"]:
            await state_manager.update_stage(
                self.workflow_id, WorkflowStage.FORKING, StageStatus.FAILED,
                fork_res["message"], error=fork_res["message"]
            )
            return False

        fork_data = fork_res["data"]
        self.state.fork_repo = fork_data["repo"]
        self.state.fork_url = fork_data["fork_url"]

        await state_manager.add_log(self.workflow_id, WorkflowStage.FORKING, f"Fork ready: {fork_data['fork_url']}")
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.FORKING, StageStatus.COMPLETED,
            f"Repository forked successfully to {fork_data['fork_url']}",
            data=fork_data
        )
        return True

    async def _run_stage_docker_setup(self) -> bool:
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.DOCKER_SETUP, StageStatus.RUNNING,
            "Initializing isolated execution environment..."
        )

        self.exec_env = get_execution_environment(self.workflow_id, prefer_docker=True)
        init_res = self.exec_env.initialize()

        if not init_res.get("success"):
            await state_manager.update_stage(
                self.workflow_id, WorkflowStage.DOCKER_SETUP, StageStatus.FAILED,
                init_res.get("message", "Container initialization failed."),
                error=init_res.get("message")
            )
            return False

        self.state.use_docker = self.exec_env.is_docker
        self.state.workspace_path = self.exec_env.workspace_dir
        self.state.docker_container_id = self.exec_env.container_id

        provider_name = "Docker Container" if self.exec_env.is_docker else "Host Isolated Sandbox"
        log_msg = f"✓ Environment ready [{provider_name}]: Python {init_res.get('python_version')}, Git {init_res.get('git_version')}"
        await state_manager.add_log(self.workflow_id, WorkflowStage.DOCKER_SETUP, log_msg)

        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.DOCKER_SETUP, StageStatus.COMPLETED,
            f"{provider_name} ready in workspace {self.state.workspace_path}",
            data=init_res
        )
        return True

    async def _run_stage_clone_and_deps(self) -> bool:
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.CLONE_AND_DEPS, StageStatus.RUNNING,
            f"Cloning forked repository from {self.state.fork_url}..."
        )

        self.repo_service = RepositoryService(self.state.workspace_path, self.exec_env)
        clone_res = self.repo_service.clone_repository(self.state.fork_url)
        if not clone_res["success"]:
            await state_manager.update_stage(
                self.workflow_id, WorkflowStage.CLONE_AND_DEPS, StageStatus.FAILED,
                clone_res["message"], error=clone_res["message"]
            )
            return False

        await state_manager.add_log(self.workflow_id, WorkflowStage.CLONE_AND_DEPS, f"✓ Cloned branch '{clone_res.get('active_branch')}' at {clone_res.get('head_commit')}")

        # Install dependencies
        await state_manager.add_log(self.workflow_id, WorkflowStage.CLONE_AND_DEPS, "Detecting project dependencies...")
        dep_res = self.repo_service.install_dependencies()
        if not dep_res.success:
            await state_manager.add_log(self.workflow_id, WorkflowStage.CLONE_AND_DEPS, f"Dependency note: {dep_res.stderr or dep_res.stdout}")

        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.CLONE_AND_DEPS, StageStatus.COMPLETED,
            "Repository cloned and dependencies configured.",
            data={"head_commit": clone_res.get("head_commit"), "active_branch": clone_res.get("active_branch")}
        )
        return True

    async def _run_stage_repo_understanding(self) -> bool:
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.REPO_UNDERSTANDING, StageStatus.RUNNING,
            "Analyzing codebase structure, modules, and issue relevance..."
        )

        analyzer = RepositoryAnalyzerAgent(self.repo_service)
        context = analyzer.analyze(self.state.issue)
        self.state.repo_context = context

        await state_manager.add_log(self.workflow_id, WorkflowStage.REPO_UNDERSTANDING, context["summary"])
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.REPO_UNDERSTANDING, StageStatus.COMPLETED,
            context["summary"],
            data={
                "relevant_files": context["relevant_files"],
                "test_files": context["test_files"],
                "keywords": context["keywords"]
            }
        )
        return True

    async def _run_stage_planner(self) -> bool:
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.PLANNER, StageStatus.RUNNING,
            "Formulating problem hypothesis, task breakdown, and testing strategy..."
        )

        planner = PlannerAgent(self.llm)
        plan = planner.plan(self.state.issue, self.state.repo_context)
        self.state.planner_output = plan

        await state_manager.add_log(self.workflow_id, WorkflowStage.PLANNER, f"Plan generated with {len(plan.implementation_tasks)} tasks.")
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.PLANNER, StageStatus.COMPLETED,
            f"Plan created: {plan.problem_understanding[:80]}...",
            data=plan.model_dump()
        )
        return True

    async def _run_stage_coder(self) -> bool:
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.CODER, StageStatus.RUNNING,
            "Implementing code changes on target repository files..."
        )

        coder = CoderAgent(self.repo_service, self.llm)
        report = coder.implement(self.state.issue, self.state.planner_output)
        self.state.coder_output = report

        diff = self.repo_service.get_git_diff()
        await state_manager.add_log(
            self.workflow_id, WorkflowStage.CODER,
            f"Coder modified {len(report.files_modified)} files, created {len(report.files_created)} files."
        )

        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.CODER, StageStatus.COMPLETED,
            report.summary_of_changes,
            data={**report.model_dump(), "git_diff": diff[:2000]}
        )
        return True

    async def _run_testing_and_debugging_loop(self) -> bool:
        tester = TesterAgent(self.repo_service, self.exec_env)
        debugger = DebuggerAgent(self.repo_service, self.llm)
        code_editor = CodeEditorAgent(self.repo_service, self.llm)

        while self.state.debug_attempts <= self.state.max_debug_attempts:
            # Run Tester
            await state_manager.update_stage(
                self.workflow_id, WorkflowStage.TESTER, StageStatus.RUNNING,
                f"Executing test suite (Attempt {self.state.debug_attempts + 1})..."
            )

            test_report = tester.run_tests(
                self.state.issue,
                self.state.planner_output,
                self.state.coder_output
            )
            self.state.test_results = test_report

            summary_msg = f"Tests: {test_report.passed_tests} passed, {test_report.failed_tests} failed (Total: {test_report.total_tests})"
            await state_manager.add_log(self.workflow_id, WorkflowStage.TESTER, summary_msg)

            if test_report.all_passed:
                await state_manager.update_stage(
                    self.workflow_id, WorkflowStage.TESTER, StageStatus.COMPLETED,
                    f"All tests passed successfully ({test_report.passed_tests}/{test_report.total_tests}).",
                    data=test_report.model_dump()
                )
                # If no debugging was needed, mark Debugger and Code Editor as NOT_REQUIRED
                if self.state.debug_attempts == 0:
                    await state_manager.update_stage(
                        self.workflow_id, WorkflowStage.DEBUGGER, StageStatus.NOT_REQUIRED,
                        "Testing passed on initial run. Debugging not required."
                    )
                    await state_manager.update_stage(
                        self.workflow_id, WorkflowStage.CODE_EDITOR, StageStatus.NOT_REQUIRED,
                        "Testing passed on initial run. Code editing not required."
                    )
                return True

            # If tests failed
            if self.state.debug_attempts >= self.state.max_debug_attempts:
                await state_manager.update_stage(
                    self.workflow_id, WorkflowStage.TESTER, StageStatus.FAILED,
                    f"Test failures persist after {self.state.max_debug_attempts} debugging attempts.",
                    data=test_report.model_dump()
                )
                return False

            # Increment debug attempt
            self.state.debug_attempts += 1
            await state_manager.add_log(
                self.workflow_id, WorkflowStage.DEBUGGER,
                f"Tests failed ({test_report.failed_tests} failures). Triggering Debugger Agent (Attempt {self.state.debug_attempts}/{self.state.max_debug_attempts})..."
            )

            # Stage 10: Debugger Agent
            await state_manager.update_stage(
                self.workflow_id, WorkflowStage.DEBUGGER, StageStatus.RUNNING,
                f"Diagnosing root cause of failure (Attempt {self.state.debug_attempts})..."
            )
            debug_report = debugger.diagnose(
                self.state.issue,
                self.state.planner_output,
                self.state.coder_output,
                test_report,
                self.state.debugging_history
            )
            self.state.debugging_history.append(debug_report.model_dump())
            await state_manager.update_stage(
                self.workflow_id, WorkflowStage.DEBUGGER, StageStatus.COMPLETED,
                f"Root cause identified: {debug_report.root_cause[:80]}...",
                data=debug_report.model_dump()
            )

            # Stage 11: Code Editor Agent
            await state_manager.update_stage(
                self.workflow_id, WorkflowStage.CODE_EDITOR, StageStatus.RUNNING,
                f"Applying targeted patch from debugger (Attempt {self.state.debug_attempts})..."
            )
            editor_report = code_editor.apply_fix(debug_report)
            await state_manager.update_stage(
                self.workflow_id, WorkflowStage.CODE_EDITOR, StageStatus.COMPLETED,
                f"Applied patch: {editor_report.summary_of_changes}",
                data=editor_report.model_dump()
            )

        return False

    async def _run_stage_reviewer(self) -> bool:
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.REVIEWER, StageStatus.RUNNING,
            "Performing independent code review and security inspection..."
        )

        reviewer = ReviewerAgent(self.repo_service, self.llm)
        diff = self.repo_service.get_git_diff()
        report = reviewer.review(
            self.state.issue,
            self.state.planner_output,
            self.state.coder_output,
            self.state.test_results,
            diff
        )
        self.state.reviewer_output = report

        status_enum = StageStatus.COMPLETED if report.approved else StageStatus.FAILED
        await state_manager.add_log(self.workflow_id, WorkflowStage.REVIEWER, f"Review decision: {report.overall_status}")
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.REVIEWER, status_enum,
            f"Review: {report.overall_status} — {report.recommendation}",
            data=report.model_dump()
        )
        return report.approved

    async def _run_stage_commit_and_push(self) -> bool:
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.COMMIT_AND_PUSH, StageStatus.RUNNING,
            "Creating branch, committing changes, and pushing to user's fork..."
        )

        branch_name = f"fix/issue-{self.state.issue.number}"
        commit_message = f"fix(agent): resolve issue #{self.state.issue.number} - {self.state.issue.title}"

        push_res = self.repo_service.commit_and_push_to_fork(
            branch_name=branch_name,
            commit_message=commit_message,
            fork_url=self.state.fork_url,
            github_token=self.github.token
        )

        if not push_res["success"]:
            await state_manager.update_stage(
                self.workflow_id, WorkflowStage.COMMIT_AND_PUSH, StageStatus.FAILED,
                push_res["message"], error=push_res["message"]
            )
            return False

        # Build PR-ready summary
        pr_summary = (
            f"## Autonomous Software Engineering Agent — PR Summary\n\n"
            f"### Issue Reference\n"
            f"Resolves #{self.state.issue.number}: **{self.state.issue.title}**\n\n"
            f"### Problem Diagnosis\n"
            f"{self.state.planner_output.problem_understanding if self.state.planner_output else 'N/A'}\n\n"
            f"### Implementation Summary\n"
            f"{self.state.coder_output.summary_of_changes if self.state.coder_output else 'N/A'}\n\n"
            f"### Testing & Verification\n"
            f"- Total tests: {self.state.test_results.total_tests if self.state.test_results else 0}\n"
            f"- Passed: {self.state.test_results.passed_tests if self.state.test_results else 0}\n"
            f"- Debugging attempts: {self.state.debug_attempts}\n\n"
            f"### Review Assessment\n"
            f"- Status: {self.state.reviewer_output.overall_status if self.state.reviewer_output else 'Approved'}\n"
            f"- Assessment: {self.state.reviewer_output.issue_resolution_assessment if self.state.reviewer_output else 'N/A'}\n"
        )

        commit_report = GitCommitReport(
            branch_name=branch_name,
            commit_hash=push_res["commit_hash"],
            commit_message=commit_message,
            fork_url=self.state.fork_url,
            push_status="Success",
            git_diff=push_res["git_diff"],
            pr_ready_summary=pr_summary
        )
        self.state.commit_report = commit_report

        await state_manager.add_log(self.workflow_id, WorkflowStage.COMMIT_AND_PUSH, f"✓ Pushed branch '{branch_name}' (commit: {push_res['commit_hash']}) to {self.state.fork_url}")
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.COMMIT_AND_PUSH, StageStatus.COMPLETED,
            f"Pushed branch '{branch_name}' to {self.state.fork_url}",
            data=commit_report.model_dump()
        )
        return True

    async def _run_stage_final_report(self):
        await state_manager.update_stage(
            self.workflow_id, WorkflowStage.FINAL_REPORT, StageStatus.COMPLETED,
            "Execution completed successfully. Final delivery report generated.",
            data={
                "fork_url": self.state.fork_url,
                "commit_hash": self.state.commit_report.commit_hash if self.state.commit_report else "N/A",
                "branch": self.state.commit_report.branch_name if self.state.commit_report else "N/A",
                "pr_summary": self.state.commit_report.pr_ready_summary if self.state.commit_report else ""
            }
        )

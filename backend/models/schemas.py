from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_REQUIRED = "not_required"


class WorkflowStage(str, Enum):
    VALIDATION = "validation"
    FORKING = "forking"
    DOCKER_SETUP = "docker_setup"
    CLONE_AND_DEPS = "clone_and_deps"
    REPO_UNDERSTANDING = "repo_understanding"
    PLANNER = "planner"
    CODER = "coder"
    TESTER = "tester"
    DEBUGGER = "debugger"
    CODE_EDITOR = "code_editor"
    REVIEWER = "reviewer"
    COMMIT_AND_PUSH = "commit_and_push"
    FINAL_REPORT = "final_report"


class WorkflowRequest(BaseModel):
    repo_url: str
    issue_url_or_number: str
    github_token: Optional[str] = None
    github_username: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_provider: Optional[str] = "gemini"  # "gemini", "openai", "groq"
    llm_model: Optional[str] = None


class StageExecutionResult(BaseModel):
    stage: WorkflowStage
    status: StageStatus = StageStatus.PENDING
    title: str
    message: str = "Waiting for execution"
    data: Optional[Dict[str, Any]] = None
    logs: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class IssueMetadata(BaseModel):
    number: int
    title: str
    body: str
    author: str
    labels: List[str] = Field(default_factory=list)
    url: str
    created_at: Optional[str] = None


class PlannerReport(BaseModel):
    problem_understanding: str
    root_cause_hypothesis: str
    relevant_files: List[str] = Field(default_factory=list)
    required_modifications: List[str] = Field(default_factory=list)
    implementation_tasks: List[str] = Field(default_factory=list)
    expected_behavior: str
    testing_strategy: str


class CoderReport(BaseModel):
    files_created: List[str] = Field(default_factory=list)
    files_modified: List[str] = Field(default_factory=list)
    summary_of_changes: str
    implementation_decisions: List[str] = Field(default_factory=list)
    incomplete_tasks: List[str] = Field(default_factory=list)


class TestResultReport(BaseModel):
    __test__ = False
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    execution_errors: List[str] = Field(default_factory=list)
    test_logs: str = ""
    all_passed: bool = False
    tests_executed: bool = False


class DebuggerReport(BaseModel):
    failure_description: str
    root_cause: str
    affected_files: List[str] = Field(default_factory=list)
    proposed_correction: str
    expected_result: str


class CodeEditorReport(BaseModel):
    files_modified: List[str] = Field(default_factory=list)
    summary_of_changes: str
    remaining_concerns: Optional[str] = None


class ReviewerReport(BaseModel):
    approved: bool = False
    overall_status: str
    issue_resolution_assessment: str
    code_quality_assessment: str
    potential_bugs: List[str] = Field(default_factory=list)
    security_observations: List[str] = Field(default_factory=list)
    unresolved_concerns: List[str] = Field(default_factory=list)
    recommendation: str


class GitCommitReport(BaseModel):
    branch_name: str
    commit_hash: str
    commit_message: str
    fork_url: str
    push_status: str
    git_diff: str
    pr_ready_summary: str


class WorkflowState(BaseModel):
    workflow_id: str
    repo_url: str
    issue_input: str
    target_owner: str = ""
    target_repo: str = ""
    fork_owner: str = ""
    fork_repo: str = ""
    fork_url: str = ""
    issue: Optional[IssueMetadata] = None
    workspace_path: str = ""
    docker_container_id: Optional[str] = None
    use_docker: bool = False
    repo_context: Optional[Dict[str, Any]] = None
    planner_output: Optional[PlannerReport] = None
    coder_output: Optional[CoderReport] = None
    test_results: Optional[TestResultReport] = None
    debugging_history: List[Dict[str, Any]] = Field(default_factory=list)
    debug_attempts: int = 0
    max_debug_attempts: int = 3
    reviewer_output: Optional[ReviewerReport] = None
    commit_report: Optional[GitCommitReport] = None
    stages: Dict[str, StageExecutionResult] = Field(default_factory=dict)
    current_stage: Optional[WorkflowStage] = None
    overall_status: StageStatus = StageStatus.PENDING
    overall_message: str = "Initialized"
    created_at: str = ""
    updated_at: str = ""

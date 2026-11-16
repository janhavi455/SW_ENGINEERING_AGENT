import os
import pytest
from backend.services.github_service import GitHubService
from backend.services.docker_service import get_execution_environment
from backend.services.repository_service import RepositoryService
from backend.services.llm_service import LLMService
from backend.models.schemas import IssueMetadata, PlannerReport, CoderReport, TestResultReport, DebuggerReport
from backend.agents.repository_analyzer import RepositoryAnalyzerAgent
from backend.agents.planner import PlannerAgent
from backend.agents.coder import CoderAgent
from backend.agents.tester import TesterAgent
from backend.agents.debugger import DebuggerAgent
from backend.agents.code_editor import CodeEditorAgent
from backend.agents.reviewer import ReviewerAgent
from backend.orchestrator.state import WorkflowStateManager


def test_github_service_validation():
    gh = GitHubService()
    # Valid URL
    res = gh.validate_url("https://github.com/pallets/flask")
    assert res["success"] is True
    assert res["data"]["owner"] == "pallets"
    assert res["data"]["repo"] == "flask"

    # Invalid URL
    bad_res = gh.validate_url("https://notgithub.com/invalid")
    assert bad_res["success"] is False


def test_execution_environment():
    env = get_execution_environment("test-runner")
    init_res = env.initialize()
    assert init_res["success"] is True
    
    cmd_res = env.execute_command("python --version")
    assert cmd_res.success is True
    assert "Python" in cmd_res.stdout


def test_repository_service(tmp_path):
    # Create fake repository workspace
    workspace = tmp_path / "sample_repo"
    workspace.mkdir()
    (workspace / "main.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    (workspace / "requirements.txt").write_text("pytest\n", encoding="utf-8")

    repo_s = RepositoryService(str(workspace))
    config = repo_s.detect_project_configuration()
    assert config["is_python"] is True
    assert "requirements.txt" in config["dependency_files"]

    # File tree
    tree = repo_s.generate_file_tree()
    assert "main.py" in tree

    # Read and write
    assert "hello" in repo_s.read_file("main.py")
    repo_s.write_file("main.py", "def hello():\n    return 'antigravity'\n")
    assert "antigravity" in repo_s.read_file("main.py")


def test_agent_pipeline_deterministic(tmp_path):
    workspace = tmp_path / "agent_test_repo"
    workspace.mkdir()
    (workspace / "calculator.py").write_text(
        "def add(a, b):\n    return a - b  # Intentional bug\n", encoding="utf-8"
    )
    (workspace / "tests").mkdir()
    (workspace / "tests" / "test_calc.py").write_text(
        "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8"
    )

    env = get_execution_environment("agent-test")
    env.initialize()
    repo_s = RepositoryService(str(workspace), env)
    llm = LLMService(api_key=None)  # Use deterministic heuristic mode

    issue = IssueMetadata(
        number=1,
        title="Fix add function in calculator",
        body="The add function returns a - b instead of a + b.",
        author="tester",
        labels=["bug"],
        url="https://github.com/test/repo/issues/1"
    )

    # 1. Analyzer
    analyzer = RepositoryAnalyzerAgent(repo_s)
    context = analyzer.analyze(issue)
    assert "calculator.py" in context["relevant_files"] or len(context["directory_tree"]) > 0

    # 2. Planner
    planner = PlannerAgent(llm)
    plan = planner.plan(issue, context)
    assert plan.problem_understanding is not None

    # 3. Coder
    coder = CoderAgent(repo_s, llm)
    coder_report = coder.implement(issue, plan)
    assert coder_report.summary_of_changes is not None

    # 4. Tester
    tester = TesterAgent(repo_s, env)
    test_report = tester.run_tests(issue, plan, coder_report)
    assert test_report.tests_executed is True

    # 5. Debugger (if failed)
    if not test_report.all_passed:
        debugger = DebuggerAgent(repo_s, llm)
        debug_report = debugger.diagnose(issue, plan, coder_report, test_report, [])
        assert debug_report.root_cause is not None

        # 6. Code Editor
        editor = CodeEditorAgent(repo_s, llm)
        edit_report = editor.apply_fix(debug_report)
        assert edit_report.summary_of_changes is not None

    # 7. Reviewer
    reviewer = ReviewerAgent(repo_s, llm)
    diff = repo_s.get_git_diff()
    review_report = reviewer.review(issue, plan, coder_report, test_report, diff)
    assert review_report.overall_status in ["Approved", "Changes Requested"]

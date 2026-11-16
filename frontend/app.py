import os
import time
import requests
import streamlit as st

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT)) 
    
from backend.utils.helpers import load_env_file

load_env_file()

# ---------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------

st.set_page_config(
    page_title="Autonomous Software Engineering Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# CUSTOM CSS
# ---------------------------------------------------------

st.markdown("""
<style>
.main-header {
    font-size: 28px;
    font-weight: 700;
    margin-bottom: 4px;
}
.sub-caption {
    color: #6c757d;
    font-size: 14px;
    margin-bottom: 20px;
}
.status-badge {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 12px;
}
.badge-pending { background-color: #6c757d22; color: #6c757d; border: 1px solid #6c757d44; }
.badge-running { background-color: #0d6efd22; color: #0d6efd; border: 1px solid #0d6efd44; }
.badge-completed { background-color: #19875422; color: #198754; border: 1px solid #19875444; }
.badge-failed { background-color: #dc354522; color: #dc3545; border: 1px solid #dc354544; }
.badge-not_required { background-color: #ffc10722; color: #b78103; border: 1px solid #ffc10744; }

.stage-card {
    border: 1px solid rgba(128,128,128,0.2);
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 10px;
    background: rgba(255, 255, 255, 0.02);
}
.log-box {
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-family: Consolas, 'Courier New', monospace;
    font-size: 12px;
    padding: 10px;
    border-radius: 6px;
    max-height: 220px;
    overflow-y: auto;
    white-space: pre-wrap;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# CONSTANTS & CONFIGURATION
# ---------------------------------------------------------

BACKEND_API = os.getenv("BACKEND_API", "http://127.0.0.1:8000")

STAGE_KEYS = [
    ("validation", "1. Input Validation"),
    ("forking", "2. Repository Forking"),
    ("docker_setup", "3. Docker Environment Setup"),
    ("clone_and_deps", "4. Repository Cloning and Dependency Setup"),
    ("repo_understanding", "5. Repository Understanding"),
    ("planner", "6. Planner Agent"),
    ("coder", "7. Coder Agent"),
    ("tester", "8. Tester Agent"),
    ("debugger", "9. Debugger Agent"),
    ("code_editor", "10. Code Editor Agent"),
    ("reviewer", "11. Reviewer Agent"),
    ("commit_and_push", "12. Commit and Push"),
    ("final_report", "13. Final Report"),
]

STATUS_DISPLAY = {
    "pending": ("⚪", "badge-pending", "Pending"),
    "running": ("🔄", "badge-running", "Running"),
    "completed": ("✅", "badge-completed", "Completed"),
    "failed": ("❌", "badge-failed", "Failed"),
    "not_required": ("➖", "badge-not_required", "Not Required"),
}

# ---------------------------------------------------------
# SESSION STATE INITIALIZATION
# ---------------------------------------------------------

if "workflow_id" not in st.session_state:
    st.session_state.workflow_id = None

if "is_running" not in st.session_state:
    st.session_state.is_running = False

if "last_state" not in st.session_state:
    st.session_state.last_state = None

# ---------------------------------------------------------
# SIDEBAR: CREDENTIALS & LLM CONFIG
# ---------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Configuration")
    
    st.subheader("GitHub Authentication")
    saved_token = os.getenv("GITHUB_TOKEN", "")
    saved_user = os.getenv("GITHUB_USERNAME", "")
    
    github_token = st.text_input(
        "GitHub Personal Access Token (PAT)",
        value=saved_token,
        type="password",
        help="Requires repo scope for forking and pushing commits."
    )
    github_user = st.text_input(
        "GitHub Username",
        value=saved_user,
        help="Your GitHub account username."
    )

    st.divider()

    st.subheader("LLM Provider")
    llm_provider = st.selectbox(
        "Provider",
        options=["gemini", "openai", "groq"],
        index=0
    )
    
    default_key = os.getenv("GEMINI_API_KEY") if llm_provider == "gemini" else (os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY") or "")
    llm_api_key = st.text_input(
        f"{llm_provider.capitalize()} API Key",
        value=default_key or "",
        type="password",
        help="Leave blank to use pre-configured environment variable or offline heuristic mode."
    )
    
    llm_model = st.text_input(
        "Model Name (Optional)",
        placeholder="gemini-2.5-flash / gpt-4o / llama-3.3-70b-versatile"
    )

    st.divider()
    st.caption("Backend Server: " + BACKEND_API)
    backend_status = "🔴 Offline"
    try:
        r = requests.get(f"{BACKEND_API}/", timeout=2)
        if r.status_code == 200:
            backend_status = "🟢 Online"
    except Exception:
        pass
    st.caption(f"Status: {backend_status}")


# ---------------------------------------------------------
# MAIN INTERFACE
# ---------------------------------------------------------

st.markdown('<div class="main-header">🤖 Autonomous Software Engineering Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-caption">Autonomous end-to-end multi-agent system: Understand → Plan → Implement → Test → Debug → Review → Push</div>', unsafe_allow_html=True)

# Input Form
with st.container():
    col1, col2 = st.columns([3, 2])
    with col1:
        repo_url = st.text_input(
            "GitHub Repository URL",
            placeholder="https://github.com/owner/repository",
            value="https://github.com/pallets/flask"
        )
    with col2:
        issue_input = st.text_input(
            "GitHub Issue URL or Number",
            placeholder="e.g. 6188 or https://github.com/owner/repo/issues/6188",
            value="6188"
        )

    start_clicked = st.button("🚀 Start Building", type="primary", use_container_width=True, disabled=st.session_state.is_running)

if start_clicked:
    if not repo_url.strip() or not issue_input.strip():
        st.error("Please provide both a GitHub Repository URL and an Issue URL or Number.")
    else:
        with st.spinner("Connecting to backend and launching autonomous workflow..."):
            try:
                payload = {
                    "repo_url": repo_url.strip(),
                    "issue_url_or_number": issue_input.strip(),
                    "github_token": github_token.strip() if github_token else None,
                    "github_username": github_user.strip() if github_user else None,
                    "llm_api_key": llm_api_key.strip() if llm_api_key else None,
                    "llm_provider": llm_provider,
                    "llm_model": llm_model.strip() if llm_model else None
                }
                res = requests.post(f"{BACKEND_API}/api/workflow/start", json=payload, timeout=20)
                res.raise_for_status()
                data = res.json()
                st.session_state.workflow_id = data["workflow_id"]
                st.session_state.is_running = True
                st.success(f"Autonomous workflow launched! Execution ID: `{data['workflow_id']}`")
                time.sleep(1)
                st.rerun()
            except requests.exceptions.ConnectionError:
                st.error("Cannot connect to FastAPI backend. Ensure the server is running on http://127.0.0.1:8000.")
            except Exception as e:
                st.error(f"Failed to start workflow: {str(e)}")


# ---------------------------------------------------------
# EXECUTION MONITOR & DASHBOARD
# ---------------------------------------------------------

if st.session_state.workflow_id:
    wf_id = st.session_state.workflow_id
    
    # Fetch latest state from backend
    try:
        res = requests.get(f"{BACKEND_API}/api/workflow/{wf_id}/status", timeout=5)
        if res.status_code == 200:
            st.session_state.last_state = res.json()
            if st.session_state.last_state.get("overall_status") in ["completed", "failed"]:
                st.session_state.is_running = False
    except Exception:
        pass

    state = st.session_state.last_state

    if state:
        st.divider()

        # Header Status Bar
        overall_status = state.get("overall_status", "pending")
        col_s1, col_s2, col_s3 = st.columns([2, 3, 2])
        
        with col_s1:
            st.markdown(f"**Execution ID:** `{wf_id}`")
        with col_s2:
            st.markdown(f"**Target:** `{state.get('target_owner')}/{state.get('target_repo')}` (Issue #{state.get('issue', {}).get('number', '') if state.get('issue') else ''})")
        with col_s3:
            icon, badge_cls, label = STATUS_DISPLAY.get(overall_status, ("⚪", "badge-pending", overall_status))
            st.markdown(f"**Overall Status:** <span class='status-badge {badge_cls}'>{icon} {label}</span>", unsafe_allow_html=True)

        # Progress calculation
        stages = state.get("stages", {})
        completed_count = sum(1 for s in stages.values() if s.get("status") in ["completed", "not_required"])
        total_stages = len(STAGE_KEYS)
        progress_val = min(1.0, completed_count / total_stages)
        st.progress(progress_val)
        st.caption(f"{completed_count} of {total_stages} execution stages finalized")

        # -----------------------------------------------------
        # SEQUENTIAL STAGE TRACKER & EXPANDABLE AGENT OUTPUTS
        # -----------------------------------------------------
        st.subheader("⚙️ Autonomous Agent Workflow")

        for stage_key, stage_display_title in STAGE_KEYS:
            stage_info = stages.get(stage_key, {})
            stage_status = stage_info.get("status", "pending")
            stage_msg = stage_info.get("message", "Waiting for execution")
            stage_logs = stage_info.get("logs", [])
            stage_data = stage_info.get("data")
            stage_err = stage_info.get("error")

            icon, badge_cls, label = STATUS_DISPLAY.get(stage_status, ("⚪", "badge-pending", stage_status))

            # Render Expander for each stage
            with st.expander(f"{icon} {stage_display_title} — {label}", expanded=(stage_status in ["running", "failed"])):
                st.markdown(f"**Status:** <span class='status-badge {badge_cls}'>{icon} {label}</span> — *{stage_msg}*", unsafe_allow_html=True)
                
                if stage_err:
                    st.error(f"Error: {stage_err}")

                # Contextual Stage Data Display
                if stage_key == "validation" and stage_data:
                    st.json(stage_data)

                elif stage_key == "forking" and stage_data:
                    st.markdown(f"**Fork URL:** [{stage_data.get('fork_url')}]({stage_data.get('fork_url')})")

                elif stage_key == "docker_setup" and stage_data:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Provider", stage_data.get("provider", "N/A"))
                    c2.metric("Python", stage_data.get("python_version", "N/A"))
                    c3.metric("Git", stage_data.get("git_version", "N/A"))

                elif stage_key == "repo_understanding" and stage_data:
                    st.markdown(f"**Discovered Relevant Files:** `{stage_data.get('relevant_files')}`")
                    st.markdown(f"**Test Files:** `{stage_data.get('test_files')}`")

                elif stage_key == "planner" and stage_data:
                    st.markdown(f"**Problem Hypothesis:** {stage_data.get('root_cause_hypothesis')}")
                    st.markdown("**Implementation Tasks:**")
                    for t in stage_data.get("implementation_tasks", []):
                        st.markdown(f"- {t}")
                    st.markdown(f"**Testing Strategy:** {stage_data.get('testing_strategy')}")

                elif stage_key == "coder" and stage_data:
                    st.markdown(f"**Summary:** {stage_data.get('summary_of_changes')}")
                    st.markdown(f"**Files Modified:** `{stage_data.get('files_modified')}` | **Files Created:** `{stage_data.get('files_created')}`")
                    if stage_data.get("git_diff"):
                        with st.expander("🔍 View Initial Coder Git Diff", expanded=False):
                            st.code(stage_data.get("git_diff"), language="diff")

                elif stage_key == "tester" and stage_data:
                    t_c1, t_c2, t_c3 = st.columns(3)
                    t_c1.metric("Passed Tests", stage_data.get("passed_tests", 0))
                    t_c2.metric("Failed Tests", stage_data.get("failed_tests", 0))
                    t_c3.metric("Total Tests", stage_data.get("total_tests", 0))
                    if stage_data.get("test_logs"):
                        with st.expander("📋 Pytest Logs", expanded=False):
                            st.text(stage_data.get("test_logs"))

                elif stage_key == "debugger" and stage_data:
                    st.markdown(f"**Failure Description:** {stage_data.get('failure_description')}")
                    st.markdown(f"**Root Cause:** {stage_data.get('root_cause')}")
                    st.markdown(f"**Proposed Correction:** {stage_data.get('proposed_correction')}")

                elif stage_key == "code_editor" and stage_data:
                    st.markdown(f"**Patch Summary:** {stage_data.get('summary_of_changes')}")
                    st.markdown(f"**Affected Files:** `{stage_data.get('files_modified')}`")

                elif stage_key == "reviewer" and stage_data:
                    r_c1, r_c2 = st.columns(2)
                    r_c1.markdown(f"**Recommendation:** {stage_data.get('recommendation')}")
                    r_c2.markdown(f"**Quality:** {stage_data.get('code_quality_assessment')}")
                    st.markdown(f"**Security Observations:** {stage_data.get('security_observations')}")

                elif stage_key == "commit_and_push" and stage_data:
                    st.success(f"✓ Pushed to branch `{stage_data.get('branch_name')}` at commit `{stage_data.get('commit_hash')}`")
                    st.markdown(f"**Fork URL:** [{stage_data.get('fork_url')}]({stage_data.get('fork_url')})")
                    if stage_data.get("git_diff"):
                        with st.expander("🔍 View Complete Git Diff", expanded=True):
                            st.code(stage_data.get("git_diff"), language="diff")

                # Execution Logs Box
                if stage_logs:
                    st.markdown("**Logs:**")
                    st.markdown(f'<div class="log-box">{"".join(l + chr(10) for l in stage_logs)}</div>', unsafe_allow_html=True)

        # -----------------------------------------------------
        # FINAL EXECUTION REPORT
        # -----------------------------------------------------
        if state.get("overall_status") in ["completed", "failed"]:
            st.divider()
            st.subheader("📑 Final Execution Report")
            
            if state.get("overall_status") == "completed":
                st.success("🎉 Autonomous software engineering task completed successfully!")
            else:
                st.error("⚠️ Autonomous workflow halted due to failure.")

            rep = state.get("commit_report")
            if rep:
                st.markdown("### 🚀 PR-Ready Delivery Summary")
                st.markdown(rep.get("pr_ready_summary", ""))

            # Reset button
            if st.button("🔄 Start Another Workflow", use_container_width=True):
                st.session_state.workflow_id = None
                st.session_state.last_state = None
                st.session_state.is_running = False
                st.rerun()

    # Auto refresh if workflow is running
    if st.session_state.is_running:
        time.sleep(2)
        st.rerun()

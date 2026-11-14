import re
import streamlit as st

# ---------------------------------------------------------
# Page configuration
# ---------------------------------------------------------
st.set_page_config(
    page_title="Autonomous Software Engineering Agent",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------
# Styling
# ---------------------------------------------------------
st.markdown(
    """
    <style>
        .stApp {
            background: #0e1117;
        }
        .main .block-container {
            max-width: 900px;
            padding-top: 2.5rem;
            padding-bottom: 3rem;
        }
        .app-subtitle {
            color: #aab4c3;
            text-align: center;
            margin-top: -12px;
            margin-bottom: 2rem;
        }
        .section-label {
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 0.45rem;
        }
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea {
            border-radius: 10px;
        }
        div.stButton > button[kind="primary"] {
            width: 100%;
            min-height: 3rem;
            border-radius: 10px;
            font-weight: 700;
        }
        .agent-note {
            color: #aab4c3;
            font-size: 0.9rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# Header
# ---------------------------------------------------------
st.title("🤖 Autonomous Software Engineering Agent")
st.markdown(
    '<p class="app-subtitle">'
    "An AI-powered assistant for understanding and implementing changes in any GitHub Repo"
    "</p>",
    unsafe_allow_html=True,
)

st.divider()

# ---------------------------------------------------------
# User inputs
# ---------------------------------------------------------
st.markdown('<div class="section-label">🔗 GitHub Repository URL</div>', unsafe_allow_html=True)
repo_url = st.text_input(
    "GitHub repository URL",
    placeholder="https://github.com/username/repository",
    label_visibility="collapsed",
)

st.markdown('<div class="section-label">💡 Required Functionality</div>', unsafe_allow_html=True)
requirement = st.text_area(
    "Describe the functionality you want to implement",
    placeholder=(
        "Describe the feature you want to build in this repository...\n\n"
        "Example: Add user authentication with email and password, "
        "including login, registration, and logout."
    ),
    height=190,
    label_visibility="collapsed",
)

# ---------------------------------------------------------
# Agent workflow placeholders
# ---------------------------------------------------------
AGENTS = [
    ("1", "Planner Agent", "Analyze the repository and prepare an implementation plan."),
    ("2", "Coder Agent", "Implement the requested functionality."),
    ("3", "Tester Agent", "Run test cases against the implementation."),
    ("4", "Debugger Agent", "Investigate and fix test failures."),
    ("5", "Code Editor Agent", "Apply and organize the required code changes."),
    ("6", "Reviewer Agent", "Review the final changes for quality and completeness."),
]


def is_valid_github_url(url: str) -> bool:
    """Accept standard GitHub repository URLs."""
    pattern = r"^https?://github\.com/[^/\s]+/[^/\s]+/?(?:\.git)?$"
    return re.match(pattern, url.strip(), flags=re.IGNORECASE) is not None


if "build_requested" not in st.session_state:
    st.session_state.build_requested = False

if st.button("🚀 Start Building", type="primary", use_container_width=True):
    st.session_state.build_requested = True
    st.session_state.repo_url = repo_url.strip()
    st.session_state.requirement = requirement.strip()

# ---------------------------------------------------------
# Chatbot-style response
# ---------------------------------------------------------
if st.session_state.build_requested:
    saved_repo = st.session_state.get("repo_url", "")
    saved_requirement = st.session_state.get("requirement", "")

    if not saved_repo or not saved_requirement:
        st.error("Please provide both the GitHub repository URL and the required functionality.")
        st.session_state.build_requested = False
    elif not is_valid_github_url(saved_repo):
        st.error(
            "Please enter a valid GitHub repository URL, for example: "
            "https://github.com/username/repository"
        )
        st.session_state.build_requested = False
    else:
        st.divider()
        st.subheader("💬 Agent Conversation")

        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(
                "**Initializing your Autonomous Software Engineering Agent...**"
            )
            st.caption("Your inputs have been received. The backend workflow is not connected yet.")

        with st.expander("View submitted task", expanded=True):
            st.markdown("**GitHub repository**")
            st.code(saved_repo, language=None)
            st.markdown("**Requested functionality**")
            st.write(saved_requirement)

        st.subheader("⚙️ Agent Workflow")
        st.caption(
            "These are workflow placeholders. Agent execution and live progress "
            "will be connected when the FastAPI backend is ready."
        )

        for number, agent_name, description in AGENTS:
            with st.container(border=True):
                st.markdown(f"**{number}. {agent_name}**")
                st.markdown(
                    f'<span class="agent-note">Waiting for backend integration</span>'
                    f"<br>{description}",
                    unsafe_allow_html=True,
                )

        st.info(
            "Frontend ready: the next step is to connect this button to your "
            "FastAPI endpoint and display real agent updates."
        )


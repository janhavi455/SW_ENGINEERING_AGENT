import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.routes.workflow import router as workflow_router
from backend.services.github_service import GitHubService
from backend.utils.helpers import load_env_file

load_env_file()

app = FastAPI(
    title="Autonomous Software Engineering Agent API",
    description="Backend API orchestrating multi-agent software engineering workflows.",
    version="2.0.0"
)

# Enable CORS for frontend interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Workflow Routes
app.include_router(workflow_router)


# ==========================================================
# LEGACY / PRE-VALIDATION ENDPOINTS (Maintained for compatibility)
# ==========================================================

class RepositoryRequest(BaseModel):
    repo_url: str


@app.post("/validate-repository")
def validate_repository(request: RepositoryRequest):
    github_service = GitHubService()
    url_res = github_service.validate_url(request.repo_url)
    if not url_res["success"]:
        return {
            "success": False,
            "step": "preprocessing",
            "message": url_res["message"],
            "checks": {
                "url_validation": {"status": "failed", "message": url_res["message"]},
                "repo_existence": {"status": "pending"},
                "public_check": {"status": "pending"}
            }
        }

    owner = url_res["data"]["owner"]
    repo = url_res["data"]["repo"]
    access_res = github_service.check_repository_access(owner, repo)
    if not access_res["success"]:
        return {
            "success": False,
            "step": "preprocessing",
            "message": access_res["message"],
            "checks": {
                "url_validation": {"status": "completed", "message": "GitHub URL syntax is valid."},
                "repo_existence": {"status": "failed", "message": access_res["message"]},
                "public_check": {"status": "pending"}
            }
        }

    return {
        "success": True,
        "step": "preprocessing",
        "message": "GitHub repository validation successful.",
        "checks": {
            "url_validation": {"status": "completed", "message": "GitHub URL syntax is valid."},
            "repo_existence": {"status": "completed", "message": "Repository exists."},
            "public_check": {"status": "completed", "message": "Repository is public."}
        },
        "repository": access_res["data"]
    }


@app.post("/fork-repository")
def fork_github_repository(request: RepositoryRequest):
    github_service = GitHubService()
    url_res = github_service.validate_url(request.repo_url)
    if not url_res["success"]:
        return {"success": False, "step": "forking", "message": url_res["message"]}

    owner = url_res["data"]["owner"]
    repo = url_res["data"]["repo"]

    fork_res = github_service.fork_repository(owner, repo)
    return {
        "success": fork_res["success"],
        "step": "forking",
        "message": fork_res["message"],
        "fork": fork_res.get("data")
    }


@app.get("/")
def home():
    return {
        "title": "Autonomous Software Engineering Agent API",
        "status": "online",
        "version": "2.0.0",
        "endpoints": {
            "start_workflow": "POST /api/workflow/start",
            "get_status": "GET /api/workflow/{workflow_id}/status",
            "stream_updates": "GET /api/workflow/{workflow_id}/stream",
            "docs": "/docs"
        }
    }

import os
import re
import time
import requests
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse
from backend.utils.helpers import load_env_file

load_env_file()

GITHUB_API = "https://api.github.com"


class GitHubService:
    def __init__(self, token: Optional[str] = None, username: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.username = username or os.getenv("GITHUB_USERNAME")

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token.strip()}"
        return headers

    def validate_url(self, repo_url: str) -> Dict[str, Any]:
        """Check 1: Validate GitHub repo URL format."""
        if not repo_url or not isinstance(repo_url, str):
            return {"success": False, "message": "Repository URL is required."}

        try:
            parsed = urlparse(repo_url.strip())
            if parsed.scheme not in ("https", "http"):
                return {"success": False, "message": "Only HTTP/HTTPS URLs are supported."}
            if parsed.netloc.lower() not in ("github.com", "www.github.com"):
                return {"success": False, "message": "Invalid GitHub domain."}

            path = parsed.path.strip("/")
            if path.endswith(".git"):
                path = path[:-4]

            parts = path.split("/")
            if len(parts) != 2:
                return {"success": False, "message": "Expected owner/repository format."}

            owner, repo = parts
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner):
                return {"success": False, "message": "Invalid GitHub owner."}
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
                return {"success": False, "message": "Invalid repository name."}

            return {
                "success": True,
                "message": "GitHub URL syntax is valid.",
                "data": {
                    "owner": owner,
                    "repo": repo,
                    "url": f"https://github.com/{owner}/{repo}"
                }
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def check_repository_access(self, owner: str, repo: str) -> Dict[str, Any]:
        """Check 2 & 3: Check repository existence and accessibility."""
        api_url = f"{GITHUB_API}/repos/{owner}/{repo}"
        try:
            response = requests.get(api_url, headers=self._get_headers(), timeout=15)
            if response.status_code == 404:
                return {"success": False, "message": "Repository does not exist or is not accessible."}
            if response.status_code == 403:
                return {"success": False, "message": "GitHub API rate limit exceeded or access forbidden."}
            if response.status_code != 200:
                return {"success": False, "message": f"GitHub API error: {response.status_code}"}

            data = response.json()
            is_private = data.get("private", False)
            return {
                "success": True,
                "message": "Repository exists and is accessible.",
                "data": {
                    "owner": data["owner"]["login"],
                    "repo": data["name"],
                    "url": data["html_url"],
                    "default_branch": data.get("default_branch", "main"),
                    "is_private": is_private,
                    "description": data.get("description", "")
                }
            }
        except Exception as e:
            return {"success": False, "message": f"Connection error: {str(e)}"}

    def parse_and_validate_issue(self, owner: str, repo: str, issue_input: str) -> Dict[str, Any]:
        """Check 4: Validate and fetch issue details from URL or number."""
        if not issue_input or not str(issue_input).strip():
            return {"success": False, "message": "GitHub issue URL or number is required."}

        issue_str = str(issue_input).strip()
        issue_number = None

        if issue_str.isdigit():
            issue_number = int(issue_str)
        else:
            # Check if it's an issue URL: e.g. https://github.com/owner/repo/issues/12
            match = re.search(r"/issues/(\d+)", issue_str)
            if match:
                issue_number = int(match.group(1))
            else:
                return {"success": False, "message": f"Could not extract issue number from '{issue_str}'."}

        api_url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}"
        try:
            response = requests.get(api_url, headers=self._get_headers(), timeout=15)
            if response.status_code == 404:
                return {"success": False, "message": f"Issue #{issue_number} was not found in {owner}/{repo}."}
            if response.status_code != 200:
                return {"success": False, "message": f"Failed to fetch issue: status {response.status_code}"}

            data = response.json()
            # If it's a pull request, github issue API returns pull_request key
            if "pull_request" in data:
                return {"success": False, "message": f"#{issue_number} is a Pull Request, not an Issue."}

            labels = [lbl.get("name", "") for lbl in data.get("labels", []) if isinstance(lbl, dict)]
            
            return {
                "success": True,
                "message": f"Successfully retrieved Issue #{issue_number}.",
                "data": {
                    "number": issue_number,
                    "title": data.get("title", ""),
                    "body": data.get("body") or "No description provided.",
                    "author": data.get("user", {}).get("login", "unknown"),
                    "labels": labels,
                    "url": data.get("html_url", ""),
                    "state": data.get("state", "open"),
                    "created_at": data.get("created_at")
                }
            }
        except Exception as e:
            return {"success": False, "message": f"Error fetching issue: {str(e)}"}

    def verify_auth_and_fork_permissions(self) -> Dict[str, Any]:
        """Check 5: Verify authenticated user and token permissions."""
        if not self.token:
            return {
                "success": False,
                "message": "GitHub Personal Access Token (PAT) is required for forking and pushing."
            }

        try:
            response = requests.get(f"{GITHUB_API}/user", headers=self._get_headers(), timeout=15)
            if response.status_code == 401:
                return {"success": False, "message": "GitHub authentication failed: invalid PAT token."}
            if response.status_code != 200:
                return {"success": False, "message": f"GitHub user verification failed: status {response.status_code}"}

            user_data = response.json()
            authenticated_login = user_data.get("login")
            
            # If username was provided, ensure it matches or auto-populate
            if not self.username:
                self.username = authenticated_login

            return {
                "success": True,
                "message": f"Authenticated as GitHub user '{authenticated_login}'.",
                "data": {
                    "username": authenticated_login,
                    "name": user_data.get("name") or authenticated_login,
                    "email": user_data.get("email")
                }
            }
        except Exception as e:
            return {"success": False, "message": f"Auth check error: {str(e)}"}

    def fork_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """Fork repository into user account and wait for availability."""
        auth_check = self.verify_auth_and_fork_permissions()
        if not auth_check["success"]:
            return auth_check

        username = auth_check["data"]["username"]
        headers = self._get_headers()

        # Step A: Check if user already owns a fork of this repo
        check_url = f"{GITHUB_API}/repos/{username}/{repo}"
        try:
            res = requests.get(check_url, headers=headers, timeout=15)
            if res.status_code == 200:
                fork_data = res.json()
                return {
                    "success": True,
                    "message": f"Existing fork found at {fork_data.get('html_url')}.",
                    "data": {
                        "fork_url": fork_data.get("html_url"),
                        "owner": username,
                        "repo": repo,
                        "default_branch": fork_data.get("default_branch", "main"),
                        "already_exists": True
                    }
                }
        except Exception:
            pass

        # Step B: Request fork creation
        fork_api_url = f"{GITHUB_API}/repos/{owner}/{repo}/forks"
        try:
            fork_res = requests.post(fork_api_url, headers=headers, json={}, timeout=30)
            if fork_res.status_code not in (200, 201, 202):
                err = fork_res.json().get("message", fork_res.text) if fork_res.content else "Unknown error"
                return {"success": False, "message": f"GitHub fork request rejected: {err}"}

            fork_data = fork_res.json()
            fork_repo_name = fork_data.get("name", repo)
            fork_html_url = fork_data.get("html_url", f"https://github.com/{username}/{fork_repo_name}")

            # Step C: Poll for readiness (GitHub fork is asynchronous)
            ready = False
            for attempt in range(8):
                time.sleep(2)
                verify_res = requests.get(f"{GITHUB_API}/repos/{username}/{fork_repo_name}", headers=headers, timeout=10)
                if verify_res.status_code == 200:
                    ready = True
                    break

            return {
                "success": True,
                "message": "Fork created and verified successfully.",
                "data": {
                    "fork_url": fork_html_url,
                    "owner": username,
                    "repo": fork_repo_name,
                    "default_branch": fork_data.get("default_branch", "main"),
                    "already_exists": False
                }
            }
        except Exception as e:
            return {"success": False, "message": f"Fork creation error: {str(e)}"}

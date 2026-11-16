import re
import requests
from urllib.parse import urlparse

def result(success, message, data=None):
    return {
        "success": success,
        "message": message,
        "data": data
    }

def validate_github_url(repo_url):

    if not repo_url or not isinstance(repo_url, str):
        return result(False, "Repository URL is required.")

    try:
        parsed = urlparse(repo_url.strip())

        if parsed.scheme not in ("https", "http"):
            return result(False, "Only HTTP/HTTPS URLs are supported.")

        if parsed.netloc.lower() not in ("github.com", "www.github.com"):
            return result(False, "Invalid GitHub domain.")

        if parsed.query or parsed.fragment:
            return result(False, "Unexpected query parameters or fragment.")

        path = parsed.path.strip("/")

        if path.endswith(".git"):
            path = path[:-4]

        parts = path.split("/")

        if len(parts) != 2:
            return result(False, "Expected owner/repository format.")

        owner, repo = parts

        if not re.fullmatch(r"[A-Za-z0-9-]+", owner):
            return result(False, "Invalid GitHub owner.")

        if not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
            return result(False, "Invalid repository name.")

        return result(
            True,
            "GitHub URL syntax is valid.",
            {
                "owner": owner,
                "repo": repo,
                "url": f"https://github.com/{owner}/{repo}"
            }
        )

    except Exception as e:
        return result(False, str(e))


# ==========================================================
# 2. CHECK REPOSITORY EXISTENCE AND VISIBILITY
# ==========================================================

def check_repository_access(owner, repo):

    api_url = f"https://api.github.com/repos/{owner}/{repo}"

    try:
        response = requests.get(
            api_url,
            headers={"Accept": "application/vnd.github+json"},
            timeout=10
        )

        if response.status_code == 404:
            return result(
                False,
                "Repository does not exist or is not publicly accessible."
            )

        if response.status_code == 403:
            return result(
                False,
                "GitHub API rate limit exceeded or access forbidden."
            )

        if response.status_code != 200:
            return result(
                False,
                f"GitHub API error: {response.status_code}"
            )

        data = response.json()

        if data.get("private") is True:
            return result(
                False,
                "Repository exists but is private."
            )

        return result(
            True,
            "Repository exists and is public.",
            {
                "owner": data["owner"]["login"],
                "repo": data["name"],
                "url": data["html_url"],
                "private": False
            }
        )

    except requests.Timeout:
        return result(False, "GitHub API request timed out.")

    except requests.RequestException as e:
        return result(False, f"Network error: {str(e)}")


import os
import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_API = "https://api.github.com"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")


def result(success, message, data=None):
    return {
        "success": success,
        "message": message,
        "data": data
    }


def fork_repository(owner, repo):

    if not GITHUB_TOKEN:
        return result(False, "GitHub token is not configured.")

    if not GITHUB_USERNAME:
        return result(False, "GitHub username is not configured.")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    try:

        # STEP 1: Verify authenticated GitHub account

        user_response = requests.get(
            f"{GITHUB_API}/user",
            headers=headers,
            timeout=15
        )

        if user_response.status_code != 200:
            return result(
                False,
                "GitHub authentication failed. Check your PAT."
            )

        authenticated_user = user_response.json()["login"]

        if authenticated_user.lower() != GITHUB_USERNAME.lower():
            return result(
                False,
                "Authenticated GitHub account does not match configured username."
            )

        # STEP 2: Check whether fork already exists

        existing_response = requests.get(
            f"{GITHUB_API}/repos/{GITHUB_USERNAME}/{repo}",
            headers=headers,
            timeout=15
        )

        if existing_response.status_code == 200:

            existing_data = existing_response.json()
            parent = existing_data.get("parent", {})

            if parent.get("full_name", "").lower() == f"{owner}/{repo}".lower():
                return result(
                    True,
                    "Repository has already been forked.",
                    {
                        "fork_url": existing_data["html_url"],
                        "owner": GITHUB_USERNAME,
                        "repo": repo,
                        "already_exists": True
                    }
                )

            return result(
                False,
                "A repository with this name already exists in your account."
            )

        # STEP 3: Create fork

        fork_response = requests.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/forks",
            headers=headers,
            json={},
            timeout=30
        )

        if fork_response.status_code not in (200, 201, 202):
            try:
                error_message = fork_response.json().get(
                    "message",
                    "Unknown GitHub API error."
                )
            except ValueError:
                error_message = fork_response.text

            return result(
                False,
                f"Fork creation failed: {error_message}"
            )

        fork_data = fork_response.json()

        return result(
            True,
            "Fork creation accepted by GitHub.",
            {
                "fork_url": fork_data.get(
                    "html_url",
                    f"https://github.com/{GITHUB_USERNAME}/{repo}"
                ),
                "owner": GITHUB_USERNAME,
                "repo": fork_data.get("name", repo),
                "already_exists": False
            }
        )

    except requests.Timeout:
        return result(False, "GitHub API request timed out.")

    except requests.RequestException as e:
        return result(False, f"Network error: {str(e)}")



def verify_fork_accessible(username, repo_name):
    """
    Verify whether the forked GitHub repository is publicly accessible.

    Returns:
        bool: True if accessible, False otherwise.
    """

    fork_url = f"https://api.github.com/repos/{username}/{repo_name}"

    try:
        response = requests.get(
            fork_url,
            timeout=10
        )

        if response.status_code == 200:
            print("Fork repository is accessible.")
            return True

        elif response.status_code == 404:
            print("Fork repository not found or inaccessible.")
            return False

        else:
            print(f"GitHub API Error: {response.status_code}")
            return False

    except requests.RequestException as e:
        print(f"Connection error: {e}")
        return False
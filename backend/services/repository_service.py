import os
import re
import git
from typing import Dict, Any, List, Optional, Tuple
from backend.services.docker_service import ExecutionEnvironment, CommandResult


class RepositoryService:
    def __init__(self, workspace_path: str, execution_env: Optional[ExecutionEnvironment] = None):
        self.workspace_path = os.path.abspath(workspace_path)
        self.repo_dir = self.workspace_path
        self.env = execution_env

    def clone_repository(self, clone_url: str, branch: Optional[str] = None) -> Dict[str, Any]:
        """
        Clone the repository into workspace.
        """
        try:
            if os.path.exists(self.repo_dir) and os.listdir(self.repo_dir):
                # Clean existing directory if present
                for item in os.listdir(self.repo_dir):
                    item_path = os.path.join(self.repo_dir, item)
                    if os.path.isdir(item_path):
                        import shutil
                        shutil.rmtree(item_path, ignore_errors=True)
                    else:
                        os.remove(item_path)

            os.makedirs(self.repo_dir, exist_ok=True)
            
            # Use git clone
            git.Repo.clone_from(clone_url, self.repo_dir, branch=branch)
            repo = git.Repo(self.repo_dir)
            active_branch = repo.active_branch.name

            return {
                "success": True,
                "message": f"Successfully cloned repository into {self.repo_dir}.",
                "active_branch": active_branch,
                "head_commit": repo.head.commit.hexsha[:8]
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Repository clone failed: {str(e)}"
            }

    def detect_project_configuration(self) -> Dict[str, Any]:
        """
        Inspect the repository for language, dependency files, and test frameworks.
        """
        files = os.listdir(self.repo_dir) if os.path.exists(self.repo_dir) else []
        
        dep_files = []
        for df in ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile", "setup.cfg"]:
            if os.path.exists(os.path.join(self.repo_dir, df)):
                dep_files.append(df)

        has_tests = False
        test_dir = os.path.join(self.repo_dir, "tests")
        if os.path.exists(test_dir) and os.path.isdir(test_dir):
            has_tests = True
        else:
            # Check for test_*.py
            for root, _, filenames in os.walk(self.repo_dir):
                if any(f.startswith("test_") or f.endswith("_test.py") for f in filenames):
                    has_tests = True
                    break

        return {
            "is_python": bool(dep_files or any(f.endswith(".py") for f in files)),
            "dependency_files": dep_files,
            "has_tests": has_tests,
            "testing_framework": "pytest" if has_tests else "unknown"
        }

    def install_dependencies(self) -> CommandResult:
        """
        Install project dependencies inside the execution environment.
        """
        if not self.env:
            return CommandResult(-1, "", "Execution environment not set.")

        config = self.detect_project_configuration()
        dep_files = config.get("dependency_files", [])

        if not dep_files:
            return CommandResult(0, "No standard dependency file found. Skipping package install.", "")

        logs = []
        for df in dep_files:
            if df == "requirements.txt":
                cmd = "pip install -r requirements.txt"
                logs.append(f"Running: {cmd}")
                res = self.env.execute_command(cmd, workdir=self.repo_dir)
                logs.append(res.stdout or res.stderr)
                if not res.success:
                    return CommandResult(res.exit_code, "\n".join(logs), res.stderr)
            elif df == "setup.py":
                cmd = "pip install -e ."
                logs.append(f"Running: {cmd}")
                res = self.env.execute_command(cmd, workdir=self.repo_dir)
                logs.append(res.stdout or res.stderr)
            elif df == "pyproject.toml":
                cmd = "pip install -e ."
                logs.append(f"Running: {cmd}")
                res = self.env.execute_command(cmd, workdir=self.repo_dir)
                logs.append(res.stdout or res.stderr)

        return CommandResult(0, "\n".join(logs), "")

    def generate_file_tree(self, max_depth: int = 4, max_files: int = 150) -> str:
        """
        Generate a clean directory tree string excluding ignored folders.
        """
        ignored_dirs = {".git", "__pycache__", "venv", ".pytest_cache", ".tox", ".mypy_cache", ".idea", ".vscode", "build", "dist", "node_modules"}
        lines = []
        total_files = 0

        def _walk(current_path: str, prefix: str, depth: int):
            nonlocal total_files
            if depth > max_depth or total_files >= max_files:
                return
            try:
                entries = sorted(os.listdir(current_path))
            except PermissionError:
                return

            dirs = [e for e in entries if os.path.isdir(os.path.join(current_path, e)) and e not in ignored_dirs]
            files = [e for e in entries if os.path.isfile(os.path.join(current_path, e))]

            for d in dirs:
                lines.append(f"{prefix}📁 {d}/")
                _walk(os.path.join(current_path, d), prefix + "  ", depth + 1)

            for f in files:
                if total_files < max_files:
                    lines.append(f"{prefix}📄 {f}")
                    total_files += 1
                elif total_files == max_files:
                    lines.append(f"{prefix}... (more files truncated)")
                    total_files += 1
                    return

        lines.append(f"📁 {os.path.basename(self.repo_dir)}/")
        _walk(self.repo_dir, "  ", 1)
        return "\n".join(lines)

    def search_codebase(self, query_terms: List[str], max_matches: int = 25) -> List[Dict[str, Any]]:
        """
        Search source files for occurrences of keywords/terms.
        """
        ignored_dirs = {".git", "__pycache__", "venv", ".pytest_cache", "build", "dist"}
        results = []

        for root, dirs, files in os.walk(self.repo_dir):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            for file in files:
                if not file.endswith((".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".sh")):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.repo_dir).replace("\\", "/")
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    for idx, line in enumerate(lines):
                        for term in query_terms:
                            if term.lower() in line.lower():
                                results.append({
                                    "file": rel_path,
                                    "line": idx + 1,
                                    "matched_term": term,
                                    "preview": line.strip()
                                })
                                if len(results) >= max_matches:
                                    return results
                except Exception:
                    continue
        return results

    def read_file(self, rel_path: str, max_lines: int = 400) -> Optional[str]:
        """
        Read the contents of a file inside the repository.
        """
        full_path = os.path.join(self.repo_dir, rel_path)
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            return None
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[:max_lines]
                return "".join(lines)
        except Exception:
            return None

    def write_file(self, rel_path: str, content: str) -> bool:
        """
        Write or overwrite a file inside the repository.
        """
        full_path = os.path.join(self.repo_dir, rel_path)
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception:
            return False

    def get_git_diff(self) -> str:
        """
        Compute git diff of modified and staged files.
        """
        try:
            repo = git.Repo(self.repo_dir)
            # Track untracked files
            diff_text = repo.git.diff()
            if not diff_text:
                # Check staged
                diff_text = repo.git.diff("--staged")
            return diff_text or "No code changes detected in git diff."
        except Exception as e:
            return f"Error computing git diff: {str(e)}"

    def get_changed_files(self) -> List[str]:
        """
        Return list of changed, added, or modified relative file paths.
        """
        try:
            repo = git.Repo(self.repo_dir)
            changed = [item.a_path for item in repo.index.diff(None)]
            untracked = repo.untracked_files
            return list(set(changed + untracked))
        except Exception:
            return []

    def commit_and_push_to_fork(
        self,
        branch_name: str,
        commit_message: str,
        fork_url: str,
        github_token: str
    ) -> Dict[str, Any]:
        """
        Stage all changes, create branch, commit, and push to user's fork.
        """
        try:
            repo = git.Repo(self.repo_dir)

            # Ensure git author is configured
            with repo.config_writer() as cw:
                cw.set_value("user", "name", "Autonomous Software Engineering Agent")
                cw.set_value("user", "email", "agent@autonomous-swe.local")

            # Check diff before commit
            diff = self.get_git_diff()

            # Checkout or create branch
            if branch_name in [b.name for b in repo.branches]:
                repo.git.checkout(branch_name)
            else:
                repo.git.checkout("-b", branch_name)

            # Add all changes
            repo.git.add("-A")

            # Check if there are changes to commit
            if repo.is_dirty() or repo.untracked_files:
                repo.git.commit("-m", commit_message)
            else:
                return {
                    "success": False,
                    "message": "No changes to commit."
                }

            commit_hash = repo.head.commit.hexsha[:8]

            # Prepare authenticated remote URL
            # format: https://<token>@github.com/<owner>/<repo>.git
            auth_remote_url = fork_url
            if fork_url.startswith("https://github.com/"):
                auth_remote_url = fork_url.replace("https://github.com/", f"https://{github_token}@github.com/")

            # Push branch to fork
            # Set or create origin remote
            if "fork_remote" in [r.name for r in repo.remotes]:
                repo.delete_remote("fork_remote")
            remote = repo.create_remote("fork_remote", auth_remote_url)
            push_info = remote.push(refspec=f"{branch_name}:{branch_name}", force=True)

            return {
                "success": True,
                "message": f"Successfully pushed branch '{branch_name}' to fork.",
                "branch_name": branch_name,
                "commit_hash": commit_hash,
                "commit_message": commit_message,
                "fork_url": fork_url,
                "git_diff": diff
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Git commit or push failed: {str(e)}"
            }

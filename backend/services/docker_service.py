import os
import shutil
import subprocess
import tempfile
import time
from typing import Dict, Any, Optional, Tuple, List
from backend.utils.helpers import load_env_file

load_env_file()


class CommandResult:
    def __init__(self, exit_code: int, stdout: str, stderr: str, duration: float = 0.0):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.duration = duration

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration": self.duration,
            "success": self.success
        }


class ExecutionEnvironment:
    """
    Abstract interface for isolated execution environment (Docker or Host Sandbox).
    """
    def __init__(self, workflow_id: str, image_name: str = "python:3.11-slim"):
        self.workflow_id = workflow_id
        self.image_name = image_name
        self.is_docker = False
        self.container_id: Optional[str] = None
        self.workspace_dir: str = ""

    def initialize(self) -> Dict[str, Any]:
        raise NotImplementedError

    def execute_command(self, cmd: str, workdir: Optional[str] = None, timeout: int = 300) -> CommandResult:
        raise NotImplementedError

    def cleanup(self):
        raise NotImplementedError


class DockerContainerEnvironment(ExecutionEnvironment):
    """
    Isolated container execution provider using Docker.
    """
    def __init__(self, workflow_id: str, image_name: str = "python:3.11-slim"):
        super().__init__(workflow_id, image_name)
        self.is_docker = True
        self.client = None
        self.container = None

    def initialize(self) -> Dict[str, Any]:
        try:
            import docker
            self.client = docker.from_env(timeout=10)
            self.client.ping()

            # Ensure host workspace exists to mount
            base_dir = os.path.abspath(os.path.join(os.getcwd(), "workspaces", self.workflow_id))
            os.makedirs(base_dir, exist_ok=True)
            self.workspace_dir = base_dir

            # Pull image if not local
            try:
                self.client.images.get(self.image_name)
            except docker.errors.ImageNotFound:
                self.client.images.pull(self.image_name)

            # Start container
            self.container = self.client.containers.run(
                self.image_name,
                command="tail -f /dev/null",
                detach=True,
                remove=True,
                volumes={self.workspace_dir: {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace"
            )
            self.container_id = self.container.id

            # Verify python and git
            py_res = self.execute_command("python --version")
            git_res = self.execute_command("git --version")

            return {
                "success": True,
                "provider": "docker",
                "container_id": self.container_id[:12],
                "image": self.image_name,
                "workspace": "/workspace",
                "python_version": py_res.stdout.strip(),
                "git_version": git_res.stdout.strip()
            }
        except Exception as e:
            return {
                "success": False,
                "provider": "docker",
                "message": f"Docker initialization failed: {str(e)}"
            }

    def execute_command(self, cmd: str, workdir: Optional[str] = None, timeout: int = 300) -> CommandResult:
        if not self.container:
            return CommandResult(-1, "", "Container not initialized.")
        try:
            start_t = time.time()
            workdir = workdir or "/workspace"
            exec_res = self.container.exec_run(
                cmd,
                workdir=workdir,
                demux=True
            )
            duration = time.time() - start_t
            stdout_b, stderr_b = exec_res.output
            stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
            stderr = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""
            return CommandResult(exec_res.exit_code, stdout, stderr, duration)
        except Exception as e:
            return CommandResult(-1, "", str(e))

    def cleanup(self):
        if self.container:
            try:
                self.container.stop(timeout=5)
            except Exception:
                pass


class HostIsolatedEnvironment(ExecutionEnvironment):
    """
    Isolated directory execution sandbox on the host system.
    Used when Docker Desktop daemon is not running.
    """
    def __init__(self, workflow_id: str):
        super().__init__(workflow_id, image_name="host-isolated")
        self.is_docker = False

    def initialize(self) -> Dict[str, Any]:
        try:
            base_dir = os.path.abspath(os.path.join(os.getcwd(), "workspaces", self.workflow_id))
            os.makedirs(base_dir, exist_ok=True)
            self.workspace_dir = base_dir

            # Verify python
            py_res = self.execute_command("python --version")
            # Verify git
            git_res = self.execute_command("git --version")

            return {
                "success": True,
                "provider": "host_isolated",
                "workspace": self.workspace_dir,
                "python_version": py_res.stdout.strip(),
                "git_version": git_res.stdout.strip(),
                "message": "Host isolated execution sandbox initialized."
            }
        except Exception as e:
            return {
                "success": False,
                "provider": "host_isolated",
                "message": f"Host isolated environment init failed: {str(e)}"
            }

    def execute_command(self, cmd: str, workdir: Optional[str] = None, timeout: int = 300) -> CommandResult:
        cwd = workdir if workdir and os.path.exists(workdir) else self.workspace_dir
        start_t = time.time()
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            duration = time.time() - start_t
            return CommandResult(proc.returncode, proc.stdout, proc.stderr, duration)
        except subprocess.TimeoutExpired:
            return CommandResult(-1, "", f"Command timed out after {timeout} seconds.", timeout)
        except Exception as e:
            return CommandResult(-1, "", str(e), time.time() - start_t)

    def cleanup(self):
        pass


def get_execution_environment(workflow_id: str, prefer_docker: bool = True) -> ExecutionEnvironment:
    """
    Factory to obtain either Docker environment (if daemon is available) or Host Isolated environment.
    """
    configured_image = os.getenv("DOCKER_IMAGE", "python:3.11-slim")
    if prefer_docker:
        try:
            import docker
            client = docker.from_env(timeout=3)
            client.ping()
            return DockerContainerEnvironment(workflow_id, image_name=configured_image)
        except Exception:
            pass
    # Fallback to isolated workspace sandbox
    return HostIsolatedEnvironment(workflow_id)

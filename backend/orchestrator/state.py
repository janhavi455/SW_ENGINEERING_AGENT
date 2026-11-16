import asyncio
import datetime
from typing import Dict, Optional, AsyncGenerator
from backend.models.schemas import (
    WorkflowState,
    WorkflowStage,
    StageStatus,
    StageExecutionResult,
)


class WorkflowStateManager:
    """
    Manages active workflow states in-memory and handles real-time event streaming.
    """
    def __init__(self):
        self._states: Dict[str, WorkflowState] = {}
        self._queues: Dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    def create_workflow(self, workflow_id: str, repo_url: str, issue_input: str) -> WorkflowState:
        now = datetime.datetime.utcnow().isoformat()
        
        # Initialize default stages
        default_stages = {}
        stage_titles = {
            WorkflowStage.VALIDATION: "1. Pre-Execution Validation",
            WorkflowStage.FORKING: "2. Fork Repository",
            WorkflowStage.DOCKER_SETUP: "3. Docker Environment Setup",
            WorkflowStage.CLONE_AND_DEPS: "4. Clone Repository & Dependencies",
            WorkflowStage.REPO_UNDERSTANDING: "5. Repository Understanding",
            WorkflowStage.PLANNER: "6. Planner Agent",
            WorkflowStage.CODER: "7. Coder Agent",
            WorkflowStage.TESTER: "8. Tester Agent",
            WorkflowStage.DEBUGGER: "9. Debugger Agent",
            WorkflowStage.CODE_EDITOR: "10. Code Editor Agent",
            WorkflowStage.REVIEWER: "11. Reviewer Agent",
            WorkflowStage.COMMIT_AND_PUSH: "12. Commit and Push Changes",
            WorkflowStage.FINAL_REPORT: "13. Final Execution Report",
        }
        
        for stage_enum, title in stage_titles.items():
            default_stages[stage_enum.value] = StageExecutionResult(
                stage=stage_enum,
                status=StageStatus.PENDING,
                title=title,
                message="Waiting for execution"
            )

        state = WorkflowState(
            workflow_id=workflow_id,
            repo_url=repo_url,
            issue_input=issue_input,
            stages=default_stages,
            overall_status=StageStatus.PENDING,
            overall_message="Workflow created and waiting to start",
            created_at=now,
            updated_at=now
        )
        self._states[workflow_id] = state
        self._queues[workflow_id] = []
        return state

    def get_state(self, workflow_id: str) -> Optional[WorkflowState]:
        return self._states.get(workflow_id)

    async def update_stage(
        self,
        workflow_id: str,
        stage: WorkflowStage,
        status: StageStatus,
        message: str,
        data: Optional[Dict] = None,
        log_line: Optional[str] = None,
        error: Optional[str] = None
    ) -> Optional[WorkflowState]:
        state = self._states.get(workflow_id)
        if not state:
            return None

        state.updated_at = datetime.datetime.utcnow().isoformat()
        state.current_stage = stage
        
        stage_key = stage.value
        if stage_key in state.stages:
            stage_obj = state.stages[stage_key]
            stage_obj.status = status
            stage_obj.message = message
            if data is not None:
                stage_obj.data = data
            if log_line:
                stage_obj.logs.append(log_line)
            if error:
                stage_obj.error = error

        # Broadcast update to subscribers
        await self._broadcast(workflow_id, {
            "type": "stage_update",
            "stage": stage.value,
            "status": status.value,
            "message": message,
            "data": data,
            "log": log_line,
            "error": error,
            "updated_at": state.updated_at
        })
        return state

    async def add_log(self, workflow_id: str, stage: WorkflowStage, log_line: str):
        state = self._states.get(workflow_id)
        if not state:
            return
        stage_key = stage.value
        if stage_key in state.stages:
            state.stages[stage_key].logs.append(log_line)
        await self._broadcast(workflow_id, {
            "type": "log",
            "stage": stage.value,
            "log": log_line
        })

    async def update_overall_status(
        self,
        workflow_id: str,
        status: StageStatus,
        message: str
    ):
        state = self._states.get(workflow_id)
        if not state:
            return
        state.overall_status = status
        state.overall_message = message
        state.updated_at = datetime.datetime.utcnow().isoformat()
        await self._broadcast(workflow_id, {
            "type": "overall_status",
            "status": status.value,
            "message": message
        })

    async def _broadcast(self, workflow_id: str, payload: dict):
        queues = self._queues.get(workflow_id, [])
        for q in queues:
            await q.put(payload)

    async def subscribe(self, workflow_id: str) -> AsyncGenerator[dict, None]:
        if workflow_id not in self._queues:
            self._queues[workflow_id] = []
        q = asyncio.Queue()
        self._queues[workflow_id].append(q)
        try:
            # First send the initial full state
            state = self.get_state(workflow_id)
            if state:
                yield {"type": "initial_state", "state": state.model_dump()}
            while True:
                item = await q.get()
                yield item
        finally:
            if workflow_id in self._queues and q in self._queues[workflow_id]:
                self._queues[workflow_id].remove(q)


# Global singleton manager
state_manager = WorkflowStateManager()

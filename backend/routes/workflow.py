import asyncio
import json
import uuid
from fastapi import APIRouter, HTTPException, BackgroundTasks
from sse_starlette.sse import EventSourceResponse

from backend.models.schemas import WorkflowRequest, WorkflowState
from backend.orchestrator.state import state_manager
from backend.orchestrator.workflow import WorkflowOrchestrator

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.post("/start")
async def start_workflow(request: WorkflowRequest, background_tasks: BackgroundTasks):
    workflow_id = str(uuid.uuid4())[:8]
    
    # Initialize state
    state = state_manager.create_workflow(
        workflow_id=workflow_id,
        repo_url=request.repo_url,
        issue_input=request.issue_url_or_number
    )

    # Launch orchestrator in background
    orchestrator = WorkflowOrchestrator(workflow_id, request)
    background_tasks.add_task(orchestrator.run)

    return {
        "success": True,
        "workflow_id": workflow_id,
        "message": "Workflow started successfully."
    }


@router.get("/{workflow_id}/status")
async def get_workflow_status(workflow_id: str):
    state = state_manager.get_state(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return state.model_dump()


@router.get("/{workflow_id}/stream")
async def stream_workflow_updates(workflow_id: str):
    state = state_manager.get_state(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    async def event_generator():
        async for event in state_manager.subscribe(workflow_id):
            yield {
                "event": "message",
                "data": json.dumps(event)
            }

    return EventSourceResponse(event_generator())

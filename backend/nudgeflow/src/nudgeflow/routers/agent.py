from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from nudgeflow.bootstrap import AgentRuntime, get_agent_runtime
from nudgeflow.database import get_db
from nudgeflow.dependencies import get_current_user
from nudgeflow.models.user import User
from nudgeflow.schemas.agent import (
    AgentRejectRequest,
    AgentRunCreate,
    AgentRunResponse,
)
from nudgeflow.services.agent.workflow import (
    approve_and_execute,
    execute_recovered_run,
    recover_interrupted_run,
    reject_run,
    retrieve_run,
    start_run,
)
from fastapi.responses import JSONResponse


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


router = APIRouter(
    prefix="/agent/runs",
    tags=["Agent workflow"],
    default_response_class=UTF8JSONResponse,
)


@router.post("", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
def create_agent_run(
    body: AgentRunCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    runtime: AgentRuntime = Depends(get_agent_runtime),
) -> dict:
    return start_run(
        db,
        user=current_user,
        follow_up_id=body.follow_up_id,
        customer_message=body.customer_message,
        exact_message=body.exact_message,
        runtime=runtime,
    )


@router.get("/{run_id}", response_model=AgentRunResponse)
def get_agent_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    return retrieve_run(db, user=current_user, run_id=run_id)


@router.post("/{run_id}/approve", response_model=AgentRunResponse)
def approve_agent_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    runtime: AgentRuntime = Depends(get_agent_runtime),
) -> dict:
    return approve_and_execute(db, user=current_user, run_id=run_id, runtime=runtime)


@router.post("/{run_id}/reject", response_model=AgentRunResponse)
def reject_agent_run(
    run_id: int,
    body: AgentRejectRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    return reject_run(
        db,
        user=current_user,
        run_id=run_id,
        reason=body.reason if body else None,
    )


@router.post("/{run_id}/recover", response_model=AgentRunResponse)
def recover_agent_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    return recover_interrupted_run(db, user=current_user, run_id=run_id)


@router.post("/{run_id}/execute", response_model=AgentRunResponse)
def execute_recovered_agent_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    runtime: AgentRuntime = Depends(get_agent_runtime),
) -> dict:
    return execute_recovered_run(db, user=current_user, run_id=run_id, runtime=runtime)

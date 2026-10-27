"""Deterministic, persisted agent workflow services."""

import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from nudgeflow.config import settings
from nudgeflow.models.agent import AgentAuditEvent, AgentExecution, AgentRun
from nudgeflow.bootstrap import AgentRuntime
from nudgeflow.models.contact import Contact
from nudgeflow.models.follow_up import FollowUp
from nudgeflow.models.user import User
from nudgeflow.schemas.agent import AgentPlanResponse
from nudgeflow.services.agent.tools import TOOL_REGISTRY
from nudgeflow.services.agent.intent_classifier import classify_customer_message
from nudgeflow.services.agent.llm_client import get_llm_client
from nudgeflow.services.agent.message_content import (
    MessageContentResult,
    deterministic_customer_fallback,
    prepare_customer_message_content,
    prepare_exact_message_content,
)

MOCK_TOOL_NAME = "mock_messaging"
EXECUTION_LEASE = timedelta(minutes=5)
_EXECUTION_LOCK_NAMESPACE = 1313220935
_LOCAL_LOCK_GUARD = threading.Lock()
_LOCAL_EXECUTION_LOCKS: dict[int, threading.Lock] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(
    db: Session,
    *,
    tenant_id: int,
    run_id: int,
    actor_user_id: int | None,
    action: str,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AgentAuditEvent(
            tenant_id=tenant_id,
            run_id=run_id,
            actor_user_id=actor_user_id,
            action=action,
            details_json=json.dumps(details or {}, sort_keys=True),
        )
    )


def _try_execution_lock(db: Session, run_id: int) -> bool:
    """Acquire a per-run lock that survives commits and is released on disconnect."""
    if db.get_bind().dialect.name == "postgresql":
        return bool(
            db.scalar(
                text("SELECT pg_try_advisory_lock(:namespace, :run_id)"),
                {"namespace": _EXECUTION_LOCK_NAMESPACE, "run_id": run_id},
            )
        )
    # SQLite is used by the local API tests, not for production concurrency.
    with _LOCAL_LOCK_GUARD:
        lock = _LOCAL_EXECUTION_LOCKS.setdefault(run_id, threading.Lock())
    return lock.acquire(blocking=False)


def _release_execution_lock(db: Session, run_id: int) -> None:
    if db.get_bind().dialect.name == "postgresql":
        try:
            db.execute(
                text("SELECT pg_advisory_unlock(:namespace, :run_id)"),
                {"namespace": _EXECUTION_LOCK_NAMESPACE, "run_id": run_id},
            )
            db.commit()
        except Exception:
            db.rollback()
        return
    with _LOCAL_LOCK_GUARD:
        lock = _LOCAL_EXECUTION_LOCKS.get(run_id)
    if lock is not None and lock.locked():
        lock.release()


def _response(db: Session, run: AgentRun) -> dict[str, Any]:
    execution = db.scalar(
        select(AgentExecution).where(
            AgentExecution.tenant_id == run.tenant_id,
            AgentExecution.run_id == run.id,
        )
    )
    events = list(
        db.scalars(
            select(AgentAuditEvent)
            .where(
                AgentAuditEvent.tenant_id == run.tenant_id,
                AgentAuditEvent.run_id == run.id,
            )
            .order_by(AgentAuditEvent.id)
        ).all()
    )
    return {
        "id": run.id,
        "follow_up_id": run.follow_up_id,
        "status": run.status,
        "plan": {
            "follow_up_id": run.follow_up_id,
            "intended_action": run.intended_action,
            "message": run.proposed_message,
            "tool_name": run.tool_name,
        },
        "tool_name": run.tool_name,
        "proposed_message": run.proposed_message,
        "intent_classification": {
            "status": run.intent_classification_status,
            "reason": run.intent_classification_reason,
            "intent": run.predicted_intent,
            "confidence": run.intent_confidence,
            "error_code": run.intent_classification_error_code,
        },
        "message_extraction": {
            "status": run.message_extraction_status,
            "data": (
                json.loads(run.message_extraction_json)
                if run.message_extraction_json is not None
                else None
            ),
            "error_code": run.message_extraction_error_code,
        },
        "draft": {
            "status": run.draft_status,
            "source": run.draft_source,
            "error_code": run.draft_error_code,
        },
        "approval_decision": run.approval_decision,
        "approval_by_user_id": run.approval_by_user_id,
        "approval_at": run.approval_at,
        "rejection_reason": run.rejection_reason,
        "execution_lease_expires_at": run.execution_lease_expires_at,
        "tool_invocation_started_at": run.tool_invocation_started_at,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "execution": (
            {
                "id": execution.id,
                "tool_name": execution.tool_name,
                "status": execution.status,
                "result": json.loads(execution.result_json),
                "error_code": execution.error_code,
                "verified": execution.verified,
                "executed_at": execution.executed_at,
                "verified_at": execution.verified_at,
            }
            if execution
            else None
        ),
        "audit": [
            {
                "id": event.id,
                "action": event.action,
                "actor_user_id": event.actor_user_id,
                "details": json.loads(event.details_json),
                "created_at": event.created_at,
            }
            for event in events
        ],
    }


def get_run(db: Session, *, tenant_id: int, run_id: int) -> AgentRun:
    run = db.scalar(
        select(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.tenant_id == tenant_id,
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found.")
    return run


def start_run(
    db: Session,
    *,
    user: User,
    follow_up_id: int,
    customer_message: str | None = None,
    exact_message: str | None = None,
    runtime: AgentRuntime | None = None,
) -> dict[str, Any]:
    context = db.execute(
        select(FollowUp, Contact)
        .join(
            Contact,
            (Contact.id == FollowUp.contact_id)
            & (Contact.tenant_id == FollowUp.tenant_id),
        )
        .where(
            FollowUp.id == follow_up_id,
            FollowUp.tenant_id == user.tenant_id,
            Contact.tenant_id == user.tenant_id,
        )
    ).first()
    if context is None:
        raise HTTPException(status_code=404, detail="Follow-up not found.")
    follow_up, contact = context
    authorized_follow_up_id = follow_up.id
    contact_name = contact.name

    follow_up_title = follow_up.title
    # Do not keep a database transaction/connection open while cold-loading ML
    # dependencies and the local model after the tenant-scoped access check.
    db.rollback()

    if customer_message is None:
        classification = {
            "status": "not_performed",
            "reason": "missing_input",
            "intent": None,
            "confidence": None,
            "error_code": None,
        }
    else:
        try:
            classification = classify_customer_message(customer_message)
        except Exception:
            # Classification is advisory and must never prevent draft creation.
            classification = {
                "status": "error",
                "reason": None,
                "intent": None,
                "confidence": None,
                "error_code": "inference_failed",
            }
    name = contact_name.strip() or "there"
    title = follow_up_title.strip()
    if exact_message is not None:
        content_result = prepare_exact_message_content(exact_message=exact_message)
    elif customer_message is None:
        content_result = prepare_customer_message_content(
            message=None,
            contact_name=name,
            follow_up_title=title,
            llm_client=None,
        )
    else:
        try:
            content_result = prepare_customer_message_content(
                message=customer_message,
                contact_name=name,
                follow_up_title=title,
                llm_client=get_llm_client(),
            )
        except Exception as exc:
            # Keep run creation resilient while exposing a safe operational code.
            import logging

            logging.getLogger(__name__).warning(
                "Agent message preparation failed; using deterministic fallback "
                "(error_type=%s)",
                type(exc).__name__,
            )
            content_result = MessageContentResult(
                extraction_status="failed",
                extraction=None,
                extraction_error_code="message_preparation_failed",
                draft_text=deterministic_customer_fallback(name),
                draft_status="fallback",
                draft_source="deterministic",
                draft_error_code="message_preparation_failed",
            )
    message = content_result.draft_text
    if not message or not message.strip() or len(message) > 4096:
        raise HTTPException(
            status_code=422,
            detail="Outbound message must contain between 1 and 4096 characters.",
        )
    wa_enabled = runtime.whatsapp_enabled if runtime is not None else settings.whatsapp_enabled
    if settings.whatsapp_enabled:
        wa_enabled = True
    selected_tool = "whatsapp_cloud_api" if wa_enabled else MOCK_TOOL_NAME
    plan = AgentPlanResponse(
        follow_up_id=authorized_follow_up_id,
        intended_action="send_follow_up_message",
        message=message,
        tool_name=selected_tool,
    )
    run = AgentRun(
        tenant_id=user.tenant_id,
        follow_up_id=authorized_follow_up_id,
        created_by_user_id=user.id,
        intended_action=plan.intended_action,
        tool_name=plan.tool_name,
        proposed_message=plan.message,
        status="awaiting_approval",
        intent_classification_status=classification["status"],
        intent_classification_reason=classification.get("reason"),
        predicted_intent=classification.get("intent"),
        intent_confidence=classification.get("confidence"),
        intent_classification_error_code=classification.get("error_code"),
        message_extraction_status=content_result.extraction_status,
        message_extraction_json=(
            content_result.extraction.model_dump_json()
            if content_result.extraction is not None
            else None
        ),
        message_extraction_error_code=content_result.extraction_error_code,
        draft_status=content_result.draft_status,
        draft_source=content_result.draft_source,
        draft_error_code=content_result.draft_error_code,
    )
    db.add(run)
    db.flush()
    _audit(
        db,
        tenant_id=user.tenant_id,
        run_id=run.id,
        actor_user_id=user.id,
        action="run_created",
        details={
            "status": "awaiting_approval",
            "tool_name": selected_tool,
            "intent_classification_status": classification["status"],
            "message_extraction_status": content_result.extraction_status,
            "draft_status": content_result.draft_status,
            "draft_source": content_result.draft_source,
            **({"exact_message": True} if exact_message is not None else {}),
        },
    )
    db.commit()
    db.refresh(run)
    return _response(db, run)


def retrieve_run(db: Session, *, user: User, run_id: int) -> dict[str, Any]:
    return _response(db, get_run(db, tenant_id=user.tenant_id, run_id=run_id))


def reject_run(
    db: Session, *, user: User, run_id: int, reason: str | None
) -> dict[str, Any]:
    run = get_run(db, tenant_id=user.tenant_id, run_id=run_id)
    if run.status == "rejected":
        return _response(db, run)
    if run.status != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reject an agent run in '{run.status}' state.",
        )
    now = _now()
    result = db.execute(
        update(AgentRun)
        .where(
            AgentRun.id == run_id,
            AgentRun.tenant_id == user.tenant_id,
            AgentRun.status == "awaiting_approval",
        )
        .values(
            status="rejected",
            approval_decision="rejected",
            approval_by_user_id=user.id,
            approval_at=now,
            rejection_reason=reason.strip() if reason and reason.strip() else None,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Agent run state changed; reload and retry.")
    _audit(
        db,
        tenant_id=user.tenant_id,
        run_id=run_id,
        actor_user_id=user.id,
        action="approval_rejected",
        details={"status": "rejected"},
    )
    db.commit()
    return retrieve_run(db, user=user, run_id=run_id)


def _lease_expires_at(run: AgentRun) -> datetime:
    return run.execution_lease_expires_at or (run.updated_at + EXECUTION_LEASE)


def recover_interrupted_run(
    db: Session, *, user: User, run_id: int
) -> dict[str, Any]:
    """Reconcile a stale claim without ever repeating an invoked tool action."""
    run = get_run(db, tenant_id=user.tenant_id, run_id=run_id)
    if run.status != "executing":
        return _response(db, run)

    # PostgreSQL advisory locks survive the state-marker commit. A live tool call
    # holds this lock until it records its result; a crashed process releases it.
    # This prevents a stale lease from reclaiming a slow but live invocation.
    if not _try_execution_lock(db, run_id):
        db.rollback()
        return retrieve_run(db, user=user, run_id=run_id)

    try:
        db.expire_all()
        run = db.scalar(
            select(AgentRun)
            .where(AgentRun.id == run_id, AgentRun.tenant_id == user.tenant_id)
            .with_for_update()
        )
        if run is None:
            raise HTTPException(status_code=404, detail="Agent run not found.")
        if run.status != "executing" or _lease_expires_at(run) > _now():
            db.rollback()
            return retrieve_run(db, user=user, run_id=run_id)

        execution = db.scalar(
            select(AgentExecution).where(
                AgentExecution.tenant_id == user.tenant_id,
                AgentExecution.run_id == run_id,
            )
        )
        if execution is not None:
            if execution.status == "succeeded" and execution.verified and _valid_stored_result(
                execution.result_json, run_id
            ):
                run.status = "completed"
                action = "recovery_reconciled_verified_execution"
            elif execution.status == "failed":
                run.status = "failed"
                action = "recovery_reconciled_failed_execution"
            else:
                run.status = "outcome_uncertain"
                action = "recovery_outcome_uncertain"
        elif run.tool_invocation_started_at is None:
            # The durable marker is written before invoking the tool. Its absence
            # proves no call began, so an explicit execute request can safely resume.
            run.status = "ready_to_execute"
            action = "recovery_ready_to_execute"
        else:
            # The tool may have acted before the process stopped. Never resend.
            run.status = "outcome_uncertain"
            action = "recovery_outcome_uncertain"

        run.execution_token = None
        run.execution_lease_expires_at = None
        run.updated_at = _now()
        _audit(
            db,
            tenant_id=user.tenant_id,
            run_id=run_id,
            actor_user_id=user.id,
            action=action,
            details={"status": run.status},
        )
        db.commit()
        db.refresh(run)
        return _response(db, run)
    finally:
        _release_execution_lock(db, run_id)


def _valid_stored_result(result_json: str, run_id: int) -> bool:
    try:
        result = json.loads(result_json)
    except (TypeError, json.JSONDecodeError):
        return False
    return (
        isinstance(result, dict)
        and isinstance(result.get("provider"), str)
        and result.get("provider") in {"mock", "whatsapp_cloud_api"}
        and result.get("run_id") == run_id
        and result.get("accepted") is True
        and isinstance(result.get("message_id"), str)
    )


def approve_and_execute(
    db: Session,
    *,
    user: User,
    run_id: int,
    runtime: AgentRuntime | None = None,
) -> dict[str, Any]:
    run = get_run(db, tenant_id=user.tenant_id, run_id=run_id)
    if run.status == "executing":
        return recover_interrupted_run(db, user=user, run_id=run_id)
    if run.status in {"completed", "failed", "outcome_uncertain", "ready_to_execute"}:
        # Repeated approval is read-only for all terminal/recovered states.
        return _response(db, run)
    if run.status == "rejected":
        raise HTTPException(status_code=409, detail="A rejected run cannot be approved.")
    if run.status != "awaiting_approval":
        raise HTTPException(status_code=409, detail=f"Cannot approve run in '{run.status}'.")
    return _claim_and_execute(db, user=user, run=run, approving=True, runtime=runtime)


def execute_recovered_run(
    db: Session,
    *,
    user: User,
    run_id: int,
    runtime: AgentRuntime | None = None,
) -> dict[str, Any]:
    """Explicitly resume only a run proven not to have invoked its tool."""
    run = get_run(db, tenant_id=user.tenant_id, run_id=run_id)
    if run.status == "executing":
        run_response = recover_interrupted_run(db, user=user, run_id=run_id)
        if run_response["status"] != "ready_to_execute":
            return run_response
        run = get_run(db, tenant_id=user.tenant_id, run_id=run_id)
    if run.status in {"completed", "failed", "outcome_uncertain"}:
        return _response(db, run)
    if run.status == "rejected":
        raise HTTPException(status_code=409, detail="A rejected run cannot execute.")
    if run.status != "ready_to_execute":
        raise HTTPException(
            status_code=409,
            detail=f"Run must be recovered as ready_to_execute before execution; current state is '{run.status}'.",
        )
    return _claim_and_execute(db, user=user, run=run, approving=False, runtime=runtime)


def _claim_and_execute(
    db: Session,
    *,
    user: User,
    run: AgentRun,
    approving: bool,
    runtime: AgentRuntime | None = None,
) -> dict[str, Any]:
    previous_status = run.status
    token = str(uuid4())
    now = _now()
    values: dict[str, Any] = {
        "status": "executing",
        "execution_token": token,
        "execution_lease_expires_at": now + EXECUTION_LEASE,
        "tool_invocation_started_at": None,
        "updated_at": now,
    }
    if approving:
        values.update(
            approval_decision="approved",
            approval_by_user_id=user.id,
            approval_at=now,
        )
    claim = db.execute(
        update(AgentRun)
        .where(
            AgentRun.id == run.id,
            AgentRun.tenant_id == user.tenant_id,
            AgentRun.status == previous_status,
        )
        .values(**values)
    )
    if claim.rowcount != 1:
        db.rollback()
        return retrieve_run(db, user=user, run_id=run.id)
    if approving:
        _audit(
            db,
            tenant_id=user.tenant_id,
            run_id=run.id,
            actor_user_id=user.id,
            action="approval_granted",
            details={"status": "executing"},
        )
    _audit(
        db,
        tenant_id=user.tenant_id,
        run_id=run.id,
        actor_user_id=user.id,
        action="execution_claimed",
        details={"resumed_after_recovery": previous_status == "ready_to_execute"},
    )
    db.commit()
    return _invoke_claimed_run(db, user=user, run_id=run.id, token=token, runtime=runtime)


def _invoke_claimed_run(
    db: Session,
    *,
    user: User,
    run_id: int,
    token: str,
    runtime: AgentRuntime | None = None,
) -> dict[str, Any]:
    if not _try_execution_lock(db, run_id):
        db.rollback()
        return retrieve_run(db, user=user, run_id=run_id)
    try:
        run = get_run(db, tenant_id=user.tenant_id, run_id=run_id)
        if run.status != "executing" or run.execution_token != token:
            db.rollback()
            return retrieve_run(db, user=user, run_id=run_id)
        if _lease_expires_at(run) <= _now():
            run.status = "ready_to_execute"
            run.execution_token = None
            run.execution_lease_expires_at = None
            run.updated_at = _now()
            _audit(
                db,
                tenant_id=user.tenant_id,
                run_id=run_id,
                actor_user_id=user.id,
                action="recovery_ready_to_execute",
                details={"status": "ready_to_execute", "reason": "claim_expired_before_tool"},
            )
            db.commit()
            return retrieve_run(db, user=user, run_id=run_id)

        context = db.execute(
            select(FollowUp, Contact)
            .join(
                Contact,
                (Contact.id == FollowUp.contact_id)
                & (Contact.tenant_id == FollowUp.tenant_id),
            )
            .where(
                FollowUp.id == run.follow_up_id,
                FollowUp.tenant_id == user.tenant_id,
                Contact.tenant_id == user.tenant_id,
            )
        ).first()

        if context is None or not context[1].phone_number:
            return _persist_execution(
                db,
                run_id=run_id,
                tenant_id=user.tenant_id,
                actor_user_id=user.id,
                token=token,
                result={
                    "provider": run.tool_name,
                    "run_id": run_id,
                    "accepted": False,
                },
                execution_status="failed",
                run_status="failed",
                error_code="recipient_not_found",
            )

        _, contact = context
        recipient_phone = contact.phone_number

        tool = None
        if run.tool_name in TOOL_REGISTRY:
            global_tool = TOOL_REGISTRY[run.tool_name]
            from nudgeflow.services.agent.tools import (
                MockMessagingTool,
                WhatsAppCloudMessagingTool,
            )
            if not isinstance(global_tool, (MockMessagingTool, WhatsAppCloudMessagingTool)):
                tool = global_tool
        if tool is None and runtime is not None:
            tool = runtime.get_tool(run.tool_name)
        if tool is None:
            tool = TOOL_REGISTRY.get(run.tool_name)

        if tool is None:
            run.status = "ready_to_execute"
            run.execution_token = None
            run.execution_lease_expires_at = None
            run.updated_at = _now()
            _audit(
                db,
                tenant_id=user.tenant_id,
                run_id=run_id,
                actor_user_id=user.id,
                action="execution_not_started",
                details={"reason": "tool_unavailable"},
            )
            db.commit()
            return retrieve_run(db, user=user, run_id=run_id)

        # Persist the marker before calling the tool. We keep the advisory lock
        # over this commit, tool call, and result transaction. Recovery uses the
        # same lock, so it cannot mark a live invocation uncertain or restart it.
        run.tool_invocation_started_at = _now()
        _audit(
            db,
            tenant_id=user.tenant_id,
            run_id=run_id,
            actor_user_id=user.id,
            action="tool_invocation_started",
            details={"tool_name": run.tool_name},
        )
        db.commit()

        try:
            result_payload = tool.send(
                run_id=run.id,
                message=run.proposed_message,
                recipient_phone=recipient_phone,
            )
        except Exception as exc:
            provider_name = (
                "whatsapp_cloud_api" if run.tool_name == "whatsapp_cloud_api" else "mock"
            )
            return _persist_execution(
                db,
                run_id=run_id,
                tenant_id=user.tenant_id,
                actor_user_id=user.id,
                token=token,
                result={"provider": provider_name, "run_id": run_id, "accepted": None},
                execution_status="uncertain",
                run_status="outcome_uncertain",
                error_code=f"tool_error_{type(exc).__name__}",
            )

        safe_result = _safe_tool_result(result_payload, run_id)
        if (
            isinstance(result_payload, dict)
            and result_payload.get("accepted") is False
        ):
            return _persist_execution(
                db,
                run_id=run_id,
                tenant_id=user.tenant_id,
                actor_user_id=user.id,
                token=token,
                result=safe_result,
                execution_status="failed",
                run_status="failed",
                error_code="tool_not_accepted",
            )
        if not _valid_tool_result(result_payload, run_id):
            return _persist_execution(
                db,
                run_id=run_id,
                tenant_id=user.tenant_id,
                actor_user_id=user.id,
                token=token,
                result=safe_result,
                execution_status="uncertain",
                run_status="outcome_uncertain",
                error_code="invalid_or_ambiguous_tool_result",
            )
        return _persist_execution(
            db,
            run_id=run_id,
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            token=token,
            result=safe_result,
            execution_status="succeeded",
            run_status="completed",
            error_code=None,
        )
    finally:
        _release_execution_lock(db, run_id)


def _valid_tool_result(payload: Any, run_id: int) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("provider"), str)
        and payload.get("provider") in {"mock", "whatsapp_cloud_api"}
        and payload.get("run_id") == run_id
        and payload.get("accepted") is True
        and isinstance(payload.get("message_id"), str)
    )


def _safe_tool_result(payload: Any, run_id: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"provider": "unknown", "run_id": run_id, "accepted": None}
    return {
        "provider": (
            payload.get("provider")
            if isinstance(payload.get("provider"), str)
            and payload.get("provider") in {"mock", "whatsapp_cloud_api"}
            else "unknown"
        ),
        "run_id": payload.get("run_id") if isinstance(payload.get("run_id"), int) else run_id,
        "message_id": payload.get("message_id") if isinstance(payload.get("message_id"), str) else None,
        "accepted": payload.get("accepted") if isinstance(payload.get("accepted"), bool) else None,
    }


def _persist_execution(
    db: Session,
    *,
    run_id: int,
    tenant_id: int,
    actor_user_id: int,
    token: str,
    result: dict[str, Any],
    execution_status: str,
    run_status: str,
    error_code: str | None,
) -> dict[str, Any]:
    run = get_run(db, tenant_id=tenant_id, run_id=run_id)
    if run.status != "executing" or run.execution_token != token:
        db.rollback()
        current = get_run(db, tenant_id=tenant_id, run_id=run_id)
        return _response(db, current)

    execution = AgentExecution(
        tenant_id=tenant_id,
        run_id=run_id,
        tool_name=run.tool_name,
        status=execution_status,
        result_json=json.dumps(result, sort_keys=True),
        error_code=error_code,
        verified=False,
    )
    db.add(execution)
    db.flush()
    _audit(
        db,
        tenant_id=tenant_id,
        run_id=run_id,
        actor_user_id=actor_user_id,
        action="execution_recorded",
        details={"execution_id": execution.id},
    )
    if run_status == "completed":
        persisted = db.scalar(
            select(AgentExecution).where(
                AgentExecution.id == execution.id,
                AgentExecution.tenant_id == tenant_id,
                AgentExecution.run_id == run_id,
            )
        )
        verified = (
            persisted is not None
            and persisted.status == "succeeded"
            and _valid_stored_result(persisted.result_json, run_id)
        )
        if verified:
            execution.verified = True
            execution.verified_at = _now()
            _audit(
                db,
                tenant_id=tenant_id,
                run_id=run_id,
                actor_user_id=actor_user_id,
                action="execution_verified",
                details={"execution_id": execution.id, "status": "completed"},
            )
        else:
            execution.status = "uncertain"
            execution.error_code = "verification_failed"
            run_status = "outcome_uncertain"
            _audit(
                db,
                tenant_id=tenant_id,
                run_id=run_id,
                actor_user_id=actor_user_id,
                action="verification_failed",
                details={"execution_id": execution.id},
            )
    elif run_status == "outcome_uncertain":
        _audit(
            db,
            tenant_id=tenant_id,
            run_id=run_id,
            actor_user_id=actor_user_id,
            action="execution_outcome_uncertain",
            details={"execution_id": execution.id, "error_code": error_code},
        )
    else:
        _audit(
            db,
            tenant_id=tenant_id,
            run_id=run_id,
            actor_user_id=actor_user_id,
            action="execution_failed",
            details={"execution_id": execution.id, "error_code": error_code},
        )
    run.status = run_status
    run.execution_token = None
    run.execution_lease_expires_at = None
    run.updated_at = _now()
    db.commit()
    db.refresh(run)
    return _response(db, run)

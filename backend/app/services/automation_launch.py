"""Reserve a manual run before dispatch; recover its original result on retry."""
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.models.automation_launch import AutomationLaunch
from app.models.passive import ExtractionTriggerEvent, WorkflowTriggerEvent
from app.schemas.automations import RunNowResponse


def identity(automation_id: str, user_id: str, request_id: str) -> dict:
    return {"automation_id": automation_id, "user_id": user_id, "request_id": request_id}


async def recover(automation_id: str, user_id: str, request_id: str, documents: list[str]):
    receipt = await AutomationLaunch.find_one(identity(automation_id, user_id, request_id))
    if receipt is None:
        return None
    if receipt.document_uuids != documents:
        raise HTTPException(status_code=409, detail="This launch request belongs to a different document selection.")
    if receipt.response:
        return RunNowResponse.model_validate(receipt.response)
    # The response may have been lost after event creation (or broker acceptance).
    # Never enqueue again, including when broker delivery is uncertain.
    if receipt.action_type in ("workflow", "task"):
        event = await WorkflowTriggerEvent.find_one({
            "trigger_context.automation_id": automation_id,
            "trigger_context.run_by_user_id": user_id,
            "trigger_context.launch_request_id": request_id,
        })
    else:
        event = await ExtractionTriggerEvent.find_one({
            "automation_id": automation_id, "user_id": user_id,
            "trigger_context.launch_request_id": request_id,
        })
    if event:
        return response_for(receipt, str(event.id), event.status)
    raise HTTPException(status_code=409, detail="Launch outcome is not yet confirmed. Retry this request to check again; it will not start a duplicate run.")


def response_for(receipt, event_id: str, status: str = "queued") -> RunNowResponse:
    selection = receipt.selection
    return RunNowResponse(
        status=status, trigger_event_id=event_id, action_type=receipt.action_type,
        documents=[{"uuid": d["uuid"], "title": d["title"]} for d in selection["documents"]],
        document_source=selection["source"], documents_matched=selection["matched"],
    )


async def reserve(automation_id: str, user_id: str, request_id: str, documents: list[str], selection: dict, action_type: str):
    receipt = AutomationLaunch(
        **identity(automation_id, user_id, request_id), document_uuids=documents,
        selection=selection, action_type=action_type,
    )
    try:
        await receipt.insert()
        return receipt, None
    except DuplicateKeyError:
        recovered = await recover(automation_id, user_id, request_id, documents)
        if recovered is None:
            raise HTTPException(status_code=409, detail="Launch receipt is unavailable. Retry the same request.")
        return None, recovered

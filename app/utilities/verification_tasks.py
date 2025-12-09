#!/usr/bin/env python3

from app.celery_worker import celery_app
from app.utilities.verification_helpers import process_verification_approval

@celery_app.task(bind=True, queue='verification', name="tasks.verification.workflow")
def execute_global_verification(self, request_uuid: str, approver_id: str):
    """
    This task runs on the dedicated synchronization node.
    """
    print(f"Sync Node: Processing verification for {request_uuid}")
    
    result = process_verification_approval(request_uuid, approver_id)
    
    if not result['success']:
        print(f"Verification failed: {result['error']}")
        # You might want to update the DB with the error state here
        return result
    
    return {"status": "Verified", "uuid": request_uuid}

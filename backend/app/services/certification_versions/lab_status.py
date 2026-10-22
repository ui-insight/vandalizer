"""Read current assigned sample readiness without uploading or retrying work."""
from app.models.folder import SmartFolder
from app.services.access_control import get_authorized_folder
from .runtime import course_operation, current_operation
from .source_access import owned_source


def document_state(document):
    if document.task_status == 'error':
        return 'failed'
    if document.processing or document.validating or document.task_status in ('layout', 'extracting', 'ocr', 'security', 'readying', 'pending', 'processing'):
        return 'processing'
    if not document.valid or document.text_layer_rejected:
        return 'failed'
    if document.task_status == 'complete':
        return 'ready' if document.raw_text.strip() else 'failed'
    return 'unavailable'


@course_operation()
async def read_lab_status(user, module_id: str, enrollment_id: str | None = None):
    from app.services import certification_service as service
    from .enrollments import EnrollmentConflict

    exercise = service.get_exercise(module_id)
    if exercise is None:
        raise EnrollmentConflict('This module is not part of the selected course')
    expected = exercise.get('documents', [])
    result = {**service.course_identity(), 'module_id': module_id, 'state': 'not_required',
              'folder_id': None, 'folder_name': None, 'documents': [], 'credit_changed': False}
    if not expected:
        return result
    progress = await service.get_progress(user.user_id)
    assigned = progress.modules.get(module_id, {}).get('provisioned_docs', [])
    if not assigned:
        return {**result, 'state': 'not_setup'}
    operation = current_operation()
    if operation:
        folder = await SmartFolder.find_one(SmartFolder.uuid == progress.lab_folder_id,
                                           SmartFolder.user_id == user.user_id) if progress.lab_folder_id else None
    else:
        folder = await SmartFolder.find_one(SmartFolder.title == service.CERT_FOLDER_TITLE,
                                           SmartFolder.user_id == user.user_id)
    if folder and await get_authorized_folder(folder.uuid, user) is None:
        folder = None
    if folder:
        result.update(folder_id=folder.uuid, folder_name=folder.title)
    # Only original assigned references are inspected. No filename search may
    # substitute unrelated work or reveal a revoked document's title/error.
    sources = []
    if (folder and isinstance(assigned, list) and all(isinstance(value, str) for value in assigned)
            and len(assigned) == len(expected) and len(set(assigned)) == len(assigned)):
        for document_id in assigned:
            document = await owned_source(user.user_id, document_id, lab_folder_id=folder.uuid)
            if document is not None:
                sources.append(document)
    rows = []
    for filename in expected:
        matches = [document for document in sources if document.title == filename]
        document = matches[0] if len(matches) == 1 else None
        rows.append({'name': filename, 'document_id': document.uuid if document else None,
                     'state': document_state(document) if document else 'unavailable'})
    states = {row['state'] for row in rows}
    result.update(documents=rows, state=next(state for state in ('unavailable', 'failed', 'processing', 'ready') if state in states))
    return result

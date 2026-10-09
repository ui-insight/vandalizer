"""Authenticated, bounded client observations, with server-bound course identity."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationEnrollment
from app.models.certification_journey import CertificationJourneyEvent

EVENTS = ('initial_progress_load_failed', 'progress_refresh_failed', 'position_save_failed',
          'saved_lesson_displayed', 'bridge_assessment_requested')


class JourneyEventRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    enrollment_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    manifest_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    event: Literal['initial_progress_load_failed', 'progress_refresh_failed', 'position_save_failed',
                   'saved_lesson_displayed', 'bridge_assessment_requested']

    @model_validator(mode='after')
    def require_identity(self):
        if bool(self.enrollment_id) != bool(self.manifest_sha256):
            raise ValueError('Provide both enrollment and package identity')
        if not self.enrollment_id and self.event not in ('initial_progress_load_failed', 'progress_refresh_failed'):
            raise ValueError('This observation requires a known enrollment')
        return self


class JourneyEventConflict(ValueError):
    pass


async def record(user_id, request: JourneyEventRequest):
    version, manifest = None, None
    if request.enrollment_id:
        # Do not initialize or load course assets: failed course reads must be
        # observable even when the installed package itself is unavailable.
        raw = await CertificationEnrollment.get_motor_collection().find_one(
            {'uuid': request.enrollment_id, 'user_id': user_id},
            {'course_version': 1, 'manifest_sha256': 1, 'provenance': 1})
        if not raw or raw.get('manifest_sha256') != request.manifest_sha256:
            raise JourneyEventConflict('The observation could not be matched to an owned course')
        if raw.get('provenance') != 'legacy_version_unknown':
            version, manifest = raw.get('course_version'), raw.get('manifest_sha256')
    identity = dict(uuid=request.event_id, user_id=user_id, enrollment_id=request.enrollment_id,
                    course_version=version, manifest_sha256=manifest, state=request.event)
    event = CertificationJourneyEvent(**identity)
    collection = CertificationJourneyEvent.get_motor_collection()
    try:
        await collection.insert_one(event.model_dump(by_alias=True, exclude={'id'}))
    except DuplicateKeyError:
        if not await collection.find_one(identity, {'_id': 1}):
            raise JourneyEventConflict('The observation identity was already used') from None
    return {'recorded': True, 'assessment_changed': False}

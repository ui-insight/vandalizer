"""Issuance-specific completion messages, independent of later course edits.

Email providers can lose acknowledgements. Each issuance gets at most one
automatic send attempt; an uncertain attempt is retained, never blindly
resent. The durable in-app notice and credential remain available regardless.
"""
import datetime
import hashlib
import json
from html import escape
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationCompletionNotice
from app.models.notification import Notification
from .attempts import encode
from .catalog import CourseCatalogError
from .credentials import CredentialRepository
from .enrollments import EnrollmentConflict


def notice_record(credential):
    if (credential.provenance != 'versioned_course_completion' or not credential.certified_at
            or not credential.course_version or not credential.module_ids):
        raise EnrollmentConflict('Historical credential preservation is not a new completion announcement')
    count = len(credential.module_ids)
    unit = 'module' if count == 1 else 'modules'
    date = datetime.datetime.fromisoformat(credential.certified_at).date().isoformat()
    return {'schema_version': 1, 'credential_id': credential.credential_id, 'user_id': credential.user_id,
            'enrollment_id': credential.enrollment_id, 'credential_sha256': encode(credential.model_dump(mode='json'))[1],
            'learner_name': credential.learner_name, 'course_title': credential.course_title,
            'course_version': credential.course_version, 'certified_at': credential.certified_at,
            'module_count': count, 'outcome_count': len(credential.outcomes),
            'title': 'Certification earned: ' + ' '.join(credential.course_title.split()),
            'body': f'{count} required {unit} completed. {credential.course_title} · {credential.course_version}. '
                    f'Earned {date}. Your original certificate is available in your earned certificates.',
            'link': '/certification'}


def render_email(record, frontend_url):
    from app.services.email_service import _BASE_STYLE, _prefs_footer
    url = urlsplit(frontend_url)
    if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password:
        raise ValueError('A valid application URL is required for the completion message')
    base = frontend_url.rstrip('/')
    link = escape(base + record['link'], quote=True)
    body = f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(record['title'])}</title>{_BASE_STYLE}
    <style>.card {{ overflow-wrap: anywhere; }} .btn {{ max-width: 100%; box-sizing: border-box; }}
    .footer, .footer a {{ color: #9ca3af !important; }}</style></head><body>
    <div class="container" role="main"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Certification earned</h1>
      <p>{escape(record['learner_name'])}, your completion of <strong>{escape(record['course_title'])}</strong> is recorded.</p>
      <p>{escape(record['body'])}</p>
      <p>Choosing another course later keeps this original certificate and issue date.</p>
      <p><a class="btn" href="{link}">View your earned certificates</a></p>
    </div>{_prefs_footer(escape(base, quote=True))}</div></body></html>'''
    return record['title'], body


class CompletionNoticeRepository:
    @property
    def records(self):
        return CertificationCompletionNotice.get_motor_collection()

    @staticmethod
    def decode(raw):
        try:
            if hashlib.sha256(raw['record_json'].encode()).hexdigest() != raw['record_sha256']:
                raise ValueError('Changed completion notice')
            record = json.loads(raw['record_json'])
            if (record['schema_version'] != 1 or record['credential_id'] != raw['uuid']
                    or record['user_id'] != raw['user_id'] or record['enrollment_id'] != raw['enrollment_id']
                    or raw['email_state'] not in ('pending', 'sending', 'sent', 'uncertain', 'skipped')):
                raise ValueError('Changed completion notice identity')
            return record
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('The preserved completion notice failed integrity verification') from exc

    async def prepare(self, user_id, enrollment_id):
        credential = await CredentialRepository().for_enrollment(user_id, enrollment_id)
        if credential is None:
            raise EnrollmentConflict('Preserve the earned credential before announcing completion')
        record = notice_record(credential)
        payload, digest = encode(record)
        seed = CertificationCompletionNotice(uuid=credential.credential_id, user_id=user_id,
            enrollment_id=enrollment_id, record_json=payload, record_sha256=digest).model_dump(mode='python', exclude={'id'})
        try:
            await self.records.insert_one(seed)
        except DuplicateKeyError:
            pass
        saved = await self.records.find_one({'uuid': credential.credential_id, 'user_id': user_id})
        if saved is None or self.decode(saved) != record:
            raise CourseCatalogError('Completion notice differs from the original issued credential')
        return saved

    async def notify(self, raw):
        record = self.decode(raw)
        if raw.get('notification_created') is True:
            return None
        # Mongo's built-in unique _id gives insert-only deduplication even if
        # the previous acknowledgement was lost or the learner read the row.
        identity = uuid5(NAMESPACE_URL, 'vandalizer:certification-notice:' + record['credential_id']).hex
        notification = Notification(uuid=identity, user_id=record['user_id'], kind='certification_complete',
            title=record['title'], body=record['body'], link=record['link'], item_kind='certification_credential',
            item_id=record['credential_id'], item_name=record['course_title'])
        row = notification.model_dump(mode='python', exclude={'id'})
        collection = Notification.get_motor_collection()
        try:
            await collection.update_one({'_id': ObjectId(identity[:24])}, {'$setOnInsert': row}, upsert=True)
        except DuplicateKeyError:
            pass
        saved = await collection.find_one({'_id': ObjectId(identity[:24])})
        if saved is None or any(saved.get(key) != row[key] for key in
                               ('uuid', 'user_id', 'kind', 'title', 'body', 'link', 'item_kind', 'item_id', 'item_name')):
            raise CourseCatalogError('The original completion notification could not be confirmed')
        await self.records.update_one({'uuid': record['credential_id'], 'user_id': record['user_id'],
            'record_sha256': raw['record_sha256']}, {'$set': {'notification_created': True}})
        return saved

    async def email(self, raw, user, settings):
        from app.services.email_service import send_email
        record = self.decode(raw)
        if user.user_id != record['user_id']:
            raise EnrollmentConflict('The completion email recipient does not own this credential')
        if not settings.promotional_emails_enabled or not user.email:
            return False
        query = {'uuid': record['credential_id'], 'user_id': user.user_id, 'record_sha256': raw['record_sha256'], 'email_state': 'pending'}
        if (user.email_preferences or {}).get('announcements') is False:
            await self.records.update_one(query, {'$set': {'email_state': 'skipped'}})
            return False
        subject, html = render_email(record, settings.frontend_url)
        claimed = await self.records.update_one(query, {'$set': {'email_state': 'sending'}})
        if claimed.modified_count != 1:
            return False
        success = False
        try:
            success = await send_email(user.email, subject, html, settings, email_type='certification_complete')
            if success:
                from app.models.user import User
                await User.get_motor_collection().update_one({'user_id': user.user_id},
                    {'$set': {'last_marketing_email_at': datetime.datetime.now(datetime.timezone.utc)}})
            return success
        finally:
            # A failure or lost provider reply is ambiguous; do not dispatch a
            # duplicate on a completion retry. A crash leaves 'sending', which
            # also cannot be claimed again. No routine staff queue is created.
            await self.records.update_one({**query, 'email_state': 'sending'},
                {'$set': {'email_state': 'sent' if success else 'uncertain'}})

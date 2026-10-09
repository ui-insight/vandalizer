"""Execute persisted extraction inputs once and retain the exact result.

Staged integration: explicit approved HTTP dispatch; no grade, XP or credential.
An uncertain provider call is never silently retried. Recovery requires a
separate reviewed disposition; this module does not revoke running workers.
"""
import asyncio
from copy import deepcopy
import datetime
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re

from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationLabExecution
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_inputs import LabInputRepository
from .writes import require_lease

MAX_RESULT_BYTES = 8 * 1024 * 1024
EXECUTION_TIMEOUT_SECONDS = 120


def implementation_digest():
    services = Path(__file__).resolve().parents[1]
    paths = [Path(__file__), services / 'extraction_engine.py', services / 'extraction_sources.py',
             Path(__file__).with_name('learner_decisions.py'), Path(__file__).with_name('scope_proposal.py'),
             Path(__file__).with_name('repair_case.py'),
             services / 'llm_service.py', services / 'domain_prompts.py', services / 'search_set_service.py',
             services.parent / 'models/system_config.py']
    return encode({'files': {str(path.relative_to(services.parent)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
                   'packages': {name: version(name) for name in ('pydantic-ai-slim', 'pydantic', 'httpx', 'openai', 'anthropic', 'google-genai')}})[1]


def runtime_digest(config):
    # Credential rotation need not alter assessment requirements. Never store
    # credentials or raw routing configuration in a learner's receipt.
    def without_credentials(value):
        if isinstance(value, dict):
            return {key: without_credentials(item) for key, item in value.items()
                    if key.lower() not in {'api_key', 'password', 'secret', 'token', 'access_token', 'refresh_token'}}
        if isinstance(value, list):
            return [without_credentials(item) for item in value]
        return value
    return encode(without_credentials(config))[1]


def execution_plan(snapshot, system_config):
    if snapshot.get('record_kind') == 'saved_workflow_design':
        raise EnrollmentConflict('A saved workflow design is not executable lab input')
    if snapshot.get('record_kind') == 'connected_workflow_input':
        raise EnrollmentConflict('Connected workflow inputs require their own approved workflow executor')
    if snapshot.get('record_kind') is not None:
        raise EnrollmentConflict('This evidence kind is not executable extraction input')
    from app.services.extraction_engine import ExtractionEngine
    from app.services.search_set_service import effective_extraction_config
    engine = ExtractionEngine(system_config_doc=system_config, domain=snapshot['artifact']['domain'])
    override = effective_extraction_config(snapshot['artifact']) or None
    config = engine._resolve_config(override)
    info = engine.effective_model_info(override)
    if config.get('mode') not in ('one_pass', 'two_pass'):
        raise EnrollmentConflict('The assessed extraction mode must be one_pass or two_pass')
    if config.get('use_images'):
        raise EnrollmentConflict('This assessed executor requires captured text inputs; image execution is not implemented')
    model_names = {info['model'], *info.get('pass_models', {}).values()}
    if config.get('mode') == 'one_pass':
        model_names.add(config.get('one_pass', {}).get('model') or info['model'])
    configured = {item.get('name') for item in system_config.get('available_models', [])}
    if not all(model_names) or not model_names <= configured:
        raise EnrollmentConflict('Every assessed extraction pass must resolve to an explicit configured model')
    fields = snapshot['artifact']['fields']
    keys = [item['searchphrase'].strip() for item in fields]
    if not keys or len(keys) != len(set(keys)):
        raise EnrollmentConflict('Assessed extraction fields must have unique nonempty keys')
    return {'executor_id': 'saved-text-extraction.1', 'implementation_sha256': implementation_digest(),
            'runtime_config_sha256': runtime_digest(system_config), 'effective_extraction_config': config,
            'model_info': info, 'model_names': sorted(model_names), 'capture_sources': True,
            'input_snapshot_sha256': encode(snapshot)[1]}


class LabExecutionRepository:
    @property
    def records(self):
        return CertificationLabExecution.get_motor_collection()

    @staticmethod
    def decode(raw):
        try:
            if hashlib.sha256(raw['plan_json'].encode()).hexdigest() != raw['plan_sha256']:
                raise ValueError('Plan digest mismatch')
            plan = json.loads(raw['plan_json'])
            if any(plan[key] != raw[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id',
                    'course_version', 'manifest_sha256', 'input_snapshot_id')):
                raise ValueError('Plan identity mismatch')
            result = None
            authorization = None
            if raw.get('authorization_json') is not None:
                if hashlib.sha256(raw['authorization_json'].encode()).hexdigest() != raw.get('authorization_sha256'):
                    raise ValueError('Authorization digest mismatch')
                authorization = json.loads(raw['authorization_json'])
                if (authorization['run_id'] != raw['uuid'] or authorization['plan_sha256'] != raw['plan_sha256']
                        or encode(authorization['decision'])[1] != authorization['decision_sha256']
                        or authorization['decision']['uuid'] != raw.get('scope_decision_id')
                        or authorization['decision_sha256'] != raw.get('scope_decision_sha256')):
                    raise ValueError('Authorization identity mismatch')
            if plan.get('approval_requirement') and raw['state'] != 'prepared' and authorization is None:
                raise ValueError('Missing execution approval')
            if raw['state'] in ('completed', 'failed', 'uncertain'):
                if hashlib.sha256(raw['result_json'].encode()).hexdigest() != raw['result_sha256']:
                    raise ValueError('Result digest mismatch')
                result = json.loads(raw['result_json'])
                if result['run_id'] != raw['uuid'] or result['plan_sha256'] != raw['plan_sha256'] or result['status'] != raw['state']:
                    raise ValueError('Result identity mismatch')
                if result.get('authorization_sha256') != raw.get('authorization_sha256'):
                    raise ValueError('Result approval mismatch')
            elif raw['state'] not in ('prepared', 'executing') or raw.get('result_json') is not None:
                raise ValueError('Unexpected execution state')
            return {'run_id': raw['uuid'], 'state': raw['state'], 'plan': plan, 'plan_sha256': raw['plan_sha256'], 'result': result,
                    'scope_decision_id': raw.get('scope_decision_id'), 'scope_decision_sha256': raw.get('scope_decision_sha256'),
                    'authorization': authorization}
        except (ValueError, TypeError, KeyError) as exc:
            raise CourseCatalogError('The saved lab execution failed integrity verification') from exc

    async def get(self, user_id, run_id):
        raw = await self.records.find_one({'uuid': run_id, 'user_id': user_id})
        return self.decode(raw) if raw else None

    @staticmethod
    def check_operation(operation, identity):
        progress = operation.progress
        if not operation.writable:
            raise EnrollmentConflict('Assessed execution requires a writable enrollment operation')
        lease = require_lease(operation.user_id, progress.enrollment_id)
        expected = {'user_id': operation.user_id, 'enrollment_id': progress.enrollment_id,
                    'course_version': operation.package.manifest.release_id,
                    'manifest_sha256': operation.package.manifest_sha256}
        if (progress.user_id != operation.user_id or str(progress.id) != lease.progress_id
                or progress.course_version != expected['course_version']
                or any(identity.get(key) != value for key, value in expected.items())):
            raise EnrollmentConflict('The saved execution belongs to a different learner or course')
        return lease

    async def prepare(self, operation, input_snapshot_id, run_id, system_config_doc):
        from .learner_decisions import execution_requirement
        from .scope_proposal import capture_proposal
        from .repair_case import capture_repair_case
        if not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise EnrollmentConflict('Execution requires an explicit request identity')
        snapshot = await LabInputRepository().get(operation.user_id, input_snapshot_id)
        if snapshot is None:
            raise EnrollmentConflict('Prepare and verify assigned lab inputs before execution')
        if snapshot.get('record_kind') == 'saved_workflow_design':
            raise EnrollmentConflict('A saved workflow design is not executable lab input')
        if snapshot.get('record_kind') == 'connected_workflow_input':
            raise EnrollmentConflict('Connected workflow inputs require their own approved workflow executor')
        if snapshot.get('record_kind') is not None:
            raise EnrollmentConflict('This evidence kind is not executable extraction input')
        lease = self.check_operation(operation, snapshot)
        identity = {key: snapshot[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256')}
        identity.update(uuid=run_id, input_snapshot_id=input_snapshot_id)
        existing = await self.records.find_one({'uuid': run_id})
        if existing is not None:
            if any(existing.get(key) != value for key, value in identity.items()):
                raise EnrollmentConflict('This run reference was already used for different inputs')
            return self.decode(existing)
        plan = {**identity, **execution_plan(snapshot, deepcopy(system_config_doc)),
                'approval_requirement': execution_requirement(operation.package, snapshot['module_id']),
                'scope_proposal': capture_proposal(operation.package, snapshot),
                'repair_case': capture_repair_case(operation.package, snapshot),
                'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(plan)
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'plan_json': serialized, 'plan_sha256': digest, 'state': 'prepared'})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': run_id})
            if existing is None or any(existing.get(key) != value for key, value in identity.items()):
                raise EnrollmentConflict('This run reference was claimed by another operation')
        return await self.get(operation.user_id, run_id)

    async def execute(self, operation, run_id, system_config_doc, *, expected_approval=None):
        from app.services.extraction_engine import ExtractionEngine
        from .learner_decisions import LearnerDecisionRepository
        saved = await self.get(operation.user_id, run_id)
        if saved is None:
            raise EnrollmentConflict('The assessed run must be prepared before dispatch')
        plan = saved['plan']
        lease = self.check_operation(operation, plan)
        if expected_approval is not None and any(saved.get(key) != value for key, value in expected_approval.items()):
            raise EnrollmentConflict('The saved plan or scope approval changed; review this run again before execution')
        if saved['state'] != 'prepared':
            # A running, failed or uncertain request can only be inspected.
            # No timeout-based reset or automatic duplicate provider call.
            return saved
        snapshot = await LabInputRepository().get(operation.user_id, plan['input_snapshot_id'])
        if snapshot is None:
            raise EnrollmentConflict('The saved input snapshot is unavailable')
        config = deepcopy(system_config_doc)
        current = execution_plan(snapshot, config)
        if any(current[key] != plan[key] for key in current):
            raise EnrollmentConflict('Execution inputs, model settings or implementation changed after preparation; review a new run')
        authorization = await LearnerDecisionRepository().authorize(operation, saved)
        approval_fields = {}
        approval_filter = {}
        if authorization is not None:
            serialized_approval, approval_digest = encode(authorization)
            approval_fields = {'authorization_json': serialized_approval, 'authorization_sha256': approval_digest}
            approval_filter = {'scope_decision_id': saved['scope_decision_id'], 'scope_decision_sha256': saved['scope_decision_sha256']}
        await LabInputRepository._check_lease(lease)
        claimed = await self.records.update_one(
            {'uuid': run_id, 'state': 'prepared', 'plan_sha256': saved['plan_sha256'], **approval_filter},
            {'$set': {'state': 'executing', 'worker_id': lease.write_id, **approval_fields}},
        )
        if claimed.modified_count != 1:
            current = await self.get(operation.user_id, run_id)
            if current['state'] == 'prepared':
                raise EnrollmentConflict('Your scope decision changed before dispatch; review the saved decision')
            return current
        saved['authorization'] = authorization
        engine = ExtractionEngine(system_config_doc=config, domain=snapshot['artifact']['domain'])
        fields, documents = snapshot['artifact']['fields'], snapshot['documents']
        kwargs = {
            'extract_keys': [field['searchphrase'].strip() for field in fields],
            'field_metadata': [{'key': field['searchphrase'].strip(), 'is_optional': field['is_optional'], 'enum_values': field['enum_values']} for field in fields],
            'doc_texts': [document['text'] for document in documents],
            'doc_metadata': [{'uuid': document['document_id'], 'title': document['title'], 'text_markers': document['text_markers']} for document in documents],
            'extraction_config_override': plan['effective_extraction_config'], 'capture_sources': True,
        }
        started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            entities = await asyncio.wait_for(asyncio.to_thread(engine.extract, **kwargs), timeout=EXECUTION_TIMEOUT_SECONDS)
            if not isinstance(entities, list) or any(not isinstance(entity, dict) for entity in entities) or engine.skipped_doc_indices:
                raise ValueError('Incomplete extraction output')
            result = {'status': 'completed', 'entities': entities,
                      'tokens_input': engine.tokens_in, 'tokens_output': engine.tokens_out,
                      'documents_executed': [document['document_id'] for document in documents],
                      'credit_awarded': False, 'learner_decisions': [], 'outcomes_awarded': []}
            if len(encode(result)[0].encode()) > MAX_RESULT_BYTES:
                raise ValueError('Execution result exceeds receipt size limit')
        except asyncio.CancelledError:
            await asyncio.shield(self._finish(saved, lease, {'status': 'uncertain', 'reason': 'caller_cancelled', 'credit_awarded': False}, started_at))
            raise
        except TimeoutError:
            # The underlying thread may still be using the provider. Never
            # claim cancellation or retry it under the same execution ID.
            result = {'status': 'uncertain', 'reason': 'provider_timeout', 'credit_awarded': False}
        except Exception as exc:
            # Do not persist provider exception text: it can contain source
            # content or credentials. This is execution failure, not a grade.
            result = {'status': 'failed', 'reason': 'execution_error', 'error_type': type(exc).__name__, 'credit_awarded': False}
        await self._finish(saved, lease, result, started_at)
        return await self.get(operation.user_id, run_id)

    async def _finish(self, saved, lease, result, started_at):
        payload = {**result, 'run_id': saved['run_id'], 'plan_sha256': saved['plan_sha256'],
                   'authorization_sha256': encode(saved['authorization'])[1] if saved.get('authorization') is not None else None,
                   'started_at': started_at, 'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(payload)
        updated = await self.records.update_one(
            {'uuid': saved['run_id'], 'plan_sha256': saved['plan_sha256'], 'state': 'executing', 'worker_id': lease.write_id},
            {'$set': {'state': result['status'], 'result_json': serialized, 'result_sha256': digest}},
        )
        if updated.modified_count != 1:
            raise EnrollmentConflict('The execution receipt changed; inspect its saved status before continuing')

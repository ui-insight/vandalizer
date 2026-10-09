"""Build exact private JSON memo bytes from checked repair and learner accountability."""
import base64
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .attempts import encode
from .enrollments import EnrollmentConflict
from .governance_findings import embedded_execution
from .governance_preparation import GovernancePreparation
from .governance_records import GovernanceJournal, IDENTITY_KEYS
from .governance_scope import Digest, Identity
from .lab_execution import LabExecutionRepository
from .outcomes import ContractModel

Answer = Annotated[str, Field(min_length=20, max_length=5000)]


class GovernanceMemoRequest(ContractModel):
    request_id: Identity
    run_id: Identity
    result_sha256: Digest
    case_sha256: Digest
    owner_user_id: str = Field(min_length=1, max_length=300)
    intended_use: Answer
    supported_inputs: Answer
    limitations: Answer
    review_route: Answer
    consent: Literal['save_checked_capstone_memo_without_release']

    @model_validator(mode='after')
    def meaningful_answers(self):
        if any(len(getattr(self, k).strip()) < 20 for k in ('intended_use', 'supported_inputs', 'limitations', 'review_route')):
            raise ValueError('Describe intended use, supported inputs, limits and the review route in your own words')
        return self


def memo_file(body, run):
    if (run['state'] != 'completed' or run['plan']['phase'] != 'repair' or body.run_id != run['run_id']
            or body.result_sha256 != encode(run['result'])[1] or body.case_sha256 != run['plan']['case_sha256']
            or body.owner_user_id != run['plan']['user_id'] or run['result']['checks']['source_supported'] is not True
            or run['result']['repair_checks']['repair_requirements_supported'] is not True):
        raise EnrollmentConflict('A memo requires your exact source-correct same-extraction repair and your own accountable ownership')
    plan, result = run['plan'], run['result']
    snapshot = plan['input_snapshot']
    memo = {'schema_version': 1, 'kind': 'fictional_training_award_routing_memo',
        'notice': 'Private learner rehearsal only. No real award, sponsor submission, staff handoff or enabled automation.',
        'task_as_of': snapshot['case']['task_as_of'], 'owner_user_id': body.owner_user_id,
        'accountability': {k: getattr(body, k) for k in ('intended_use', 'supported_inputs', 'limitations', 'review_route')},
        'destination': {'id': 'private_training_inbox', 'audience': 'enrolled_learner_only'},
        'results': {f['field']: f['actual_value'] for f in result['checks']['fields']},
        'evidence': {'artifact_id': snapshot['artifact_id'], 'artifact_sha256': snapshot['artifact_sha256'],
            'original_run_id': plan['original_run_id'], 'original_run_sha256': plan['original_run_sha256'],
            'repair_run_id': run['run_id'], 'repair_result_sha256': body.result_sha256,
            'source_finding_id': plan['source_finding_id'], 'source_finding_sha256': plan['source_finding_sha256'],
            'scope_correction_id': plan['scope_correction_id'], 'scope_correction_sha256': plan['scope_correction_sha256'],
            'sources': [{k: source[k] for k in ('source_id', 'document_id', 'assigned_filename', 'source_sha256')} for source in snapshot['documents']],
            'complete_source_checks': result['checks'], 'repair_checks': result['repair_checks']},
        'ongoing_automation': 'disabled', 'external_delivery_authorized': False}
    serialized, digest = encode(memo)
    data = serialized.encode()
    return {'filename': 'capstone-accountable-handoff.json', 'content_type': 'application/json',
        'sha256': digest, 'byte_length': len(data), 'content_base64': base64.b64encode(data).decode(), 'memo': memo}


class GovernanceMemoRepository(GovernanceJournal):
    request_model = GovernanceMemoRequest
    prompt_id = 'governance_accountable_memo'
    channel = 'authenticated_learner_governance_memo'

    @classmethod
    def validate(cls, saved, body):
        run = GovernancePreparation.decode(saved['execution'])
        if (any(saved[k] != (run['run_id'] if k == 'run_id' else run['plan'][k]) for k in IDENTITY_KEYS)
                or saved['case'] != run['plan']['input_snapshot']['case'] or saved['file'] != memo_file(body, run)
                or saved['release_authorized'] is not False or saved['delivery_confirmed'] is not False):
            raise ValueError('The memo changed its owned repair, complete checked values or learner accountability')

    async def build(self, operation, body):
        run = await GovernancePreparation().get(operation.user_id, body.run_id)
        if run is None:
            raise EnrollmentConflict('Inspect your completed repair before preparing the accountable memo')
        LabExecutionRepository.check_operation(operation, run['plan'])
        return {'execution': embedded_execution(run), 'file': memo_file(body, run), 'release_authorized': False, 'delivery_confirmed': False}

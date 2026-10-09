"""Owned recognition receipts, read without regrading or moving progress."""
from .catalog import CourseCatalogError
from .enrollments import EnrollmentRepository
from .scenario_submissions import ScenarioSubmissionRepository, module_bank


class ScenarioHistory:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.submissions = ScenarioSubmissionRepository()

    async def resolve(self, user_id, enrollment_id, module_id):
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        return enrollment, module_bank(package, module_id)

    @staticmethod
    def receipt(raw, enrollment, bank):
        try:
            return ScenarioHistory._receipt(raw, enrollment, bank)
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            if isinstance(exc, CourseCatalogError):
                raise
            raise CourseCatalogError('The saved scenario feedback is inconsistent; the original result needs reconciliation') from exc

    @staticmethod
    def _receipt(raw, enrollment, bank):
        record = ScenarioSubmissionRepository.decode(raw)
        if (record['user_id'] != enrollment.user_id
                or record.get('submission_channel') != 'authenticated_learner_request'
                or record['enrollment_id'] != enrollment.uuid or record['module_id'] != bank.module_id
                or record['course_version'] != enrollment.course_version
                or record['manifest_sha256'] != enrollment.manifest_sha256
                or record['bank_sha256'] != bank.digest
                or record['result'].get('bank_sha256') != bank.digest
                or record['result'].get('assessment_kind') != 'scenario_recognition'
                or record['result'].get('credit_awarded') is not False):
            raise CourseCatalogError('The saved scenario result does not match its original course')
        try:
            ScenarioHistory.validate_feedback(record, bank)
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise CourseCatalogError('The saved scenario feedback is inconsistent; the original result needs reconciliation') from exc
        return record

    @staticmethod
    def validate_feedback(record, bank):
        """Validate the receipt's own summaries without running the grader.

        Historical verdicts are retained. This does not re-decide whether a
        chosen answer was correct or rewrite its original feedback.
        """
        result, answers = record['result'], record['answers']
        if (result['bank_id'] != bank.bank_id or result['rubric_id'] != bank.rubric_id
                or type(result['passed']) is not bool or not isinstance(answers, dict)
                or set(answers) - {question.id for question in bank.questions}):
            raise ValueError('Invalid scenario result identity or answer set')
        checks, outcomes = result['checks'], result['outcomes']
        if (not isinstance(checks, list) or len(checks) != len(bank.questions)
                or len({check['id'] for check in checks}) != len(checks)
                or {check['id'] for check in checks} != {question.id for question in bank.questions}
                or not isinstance(outcomes, list) or len(outcomes) != len(bank.outcome_ids)
                or {outcome['outcome_id'] for outcome in outcomes} != set(bank.outcome_ids)):
            raise ValueError('Scenario feedback coverage is incomplete or duplicated')
        by_id = {check['id']: check for check in checks}
        for question in bank.questions:
            check = by_id[question.id]
            answer = answers.get(question.id)
            if answer is not None and answer not in {choice.id for choice in question.choices}:
                raise ValueError('An original chosen answer is unavailable')
            if (check['outcome_id'] != question.outcome_id or check['role'] != 'required'
                    or type(check['passed']) is not bool or not isinstance(check['name'], str)
                    or not isinstance(check['detail'], str) or not check['detail'].strip()):
                raise ValueError('Scenario check has an invalid outcome, verdict or explanation')
        for outcome in outcomes:
            if (type(outcome['passed']) is not bool
                    or outcome['passed'] is not all(check['passed'] for check in checks if check['outcome_id'] == outcome['outcome_id'])):
                raise ValueError('Scenario outcome summary contradicts its saved checks')
        if result['passed'] is not all(check['passed'] for check in checks):
            raise ValueError('Scenario result summary contradicts its saved checks')

    async def attempts(self, user_id, enrollment_id, module_id):
        enrollment, bank = await self.resolve(user_id, enrollment_id, module_id)
        rows = await self.submissions.records.find({'user_id': user_id, 'enrollment_id': enrollment_id,
            'module_id': module_id}).sort('_id', -1).limit(51).to_list(51)
        records = [self.receipt(row, enrollment, bank) for row in rows[:50]]
        return {'enrollment_id': enrollment_id, 'module_id': module_id, 'bank_sha256': bank.digest,
                'read_only': True, 'older_attempts_available': len(rows) > 50,
                'attempts': [{'attempt_id': record['uuid'], 'submitted_at': record['submitted_at'],
                              'passed': record['result']['passed']} for record in records]}

    async def attempt(self, user_id, enrollment_id, module_id, attempt_id):
        enrollment, bank = await self.resolve(user_id, enrollment_id, module_id)
        raw = await self.submissions.records.find_one({'uuid': attempt_id, 'user_id': user_id,
            'enrollment_id': enrollment_id, 'module_id': module_id})
        if raw is None:
            return None
        record = self.receipt(raw, enrollment, bank)
        checks = {check['id']: check for check in record['result']['checks']}
        if len(checks) != len(bank.questions) or set(checks) != {question.id for question in bank.questions}:
            raise CourseCatalogError('The saved scenario feedback is incomplete')
        questions = []
        for question in bank.questions:
            answer = record['answers'].get(question.id)
            choice = next((item for item in question.choices if item.id == answer), None)
            if answer is not None and choice is None:
                raise CourseCatalogError('The saved scenario choice is unavailable in its original bank')
            check = checks[question.id]
            questions.append({'id': question.id, 'prompt': question.prompt,
                              'chosen_answer': choice.text if choice else None,
                              'passed': check['passed'], 'feedback': check['detail']})
        return {'enrollment_id': enrollment_id, 'module_id': module_id, 'attempt_id': attempt_id,
                'bank_sha256': bank.digest, 'submitted_at': record['submitted_at'],
                'read_only': True, 'assessment_kind': 'scenario_recognition', 'credit_awarded': False,
                'passed': record['result']['passed'], 'questions': questions}

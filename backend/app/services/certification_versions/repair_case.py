"""Authored repair specimens, never provider execution or learner evidence.

This validates a draft case and its package binding. It does not enable practical
delivery, collect learner work, grade a response or award credit.
"""
import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .attempts import encode
from .catalog import CourseCatalogError


class CaseModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class SpecimenField(CaseModel):
    title: str = Field(min_length=1, max_length=200)
    searchphrase: str = Field(min_length=10, max_length=2000)
    is_optional: bool = Field(strict=True)
    enum_values: tuple[str, ...] = ()


class FlawedSpecimen(CaseModel):
    provenance: Literal['authored_flawed_example_not_an_execution']
    notice: str = Field(min_length=40, max_length=1000)
    fields: tuple[SpecimenField, ...] = Field(min_length=1, max_length=20)
    output: dict[str, str | None]

    @model_validator(mode='after')
    def matching_fields(self):
        titles = [field.title for field in self.fields]
        if len(set(titles)) != len(titles) or set(titles) != set(self.output):
            raise ValueError('The authored specimen needs one output for each unique field')
        return self


class SourceAnchor(CaseModel):
    page: int = Field(ge=1, strict=True)
    quote: str = Field(min_length=3, max_length=2000)


class RepairExpectation(CaseModel):
    field: str = Field(min_length=1, max_length=200)
    expected_value: str | None
    meaning: str = Field(min_length=20, max_length=2000)
    absence_policy: Literal['required_source_value', 'absent_when_unnamed']
    allowed_categories: tuple[str, ...] = ()
    anchors: tuple[SourceAnchor, ...] = Field(min_length=1, max_length=5)

    @model_validator(mode='after')
    def consistent_expectation(self):
        if ((self.expected_value is None) != (self.absence_policy == 'absent_when_unnamed')
                or (self.allowed_categories and self.expected_value not in self.allowed_categories)
                or len(set(self.allowed_categories)) != len(self.allowed_categories)):
            raise ValueError('Expected absence and categories must agree with the source value')
        return self


class ExtractionRepairCase(CaseModel):
    schema_version: Literal[1] = 1
    id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1, strict=True)
    module_id: Literal['extraction_engine']
    source_filename: Literal['nih-r01-neuroscience.pdf']
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    task: str = Field(min_length=50, max_length=3000)
    scope_prompt_id: str
    value_prompt_id: str
    outcome_ids: tuple[str, ...] = Field(min_length=3, max_length=3)
    baseline: FlawedSpecimen
    expectations: tuple[RepairExpectation, ...] = Field(min_length=1, max_length=20)
    evidence_rule: Literal['authored_baseline_plus_owned_revised_run_and_authenticated_source_checks']

    @model_validator(mode='after')
    def coherent_case(self):
        fields = [item.field for item in self.expectations]
        if (len(set(fields)) != len(fields) or set(fields) != set(self.baseline.output)
                or len(set(self.outcome_ids)) != len(self.outcome_ids)
                or any(not item.startswith('extraction_engine.') for item in self.outcome_ids)
                or self.scope_prompt_id == self.value_prompt_id):
            raise ValueError('Repair case fields, outcomes and decision identities must be unambiguous')
        if not any(self.baseline.output[item.field] != item.expected_value for item in self.expectations):
            raise ValueError('A repair case must contain an actual authored error')
        return self

    @property
    def digest(self):
        return encode(self.model_dump(mode='json'))[1]

    def verify_contract(self, contract, prompts):
        module = next((module for module in contract.modules if module.module_id == self.module_id), None)
        by_prompt = {prompt.id: prompt for prompt in prompts}
        if module is None or set(self.outcome_ids) != {outcome.id for outcome in module.outcomes}:
            raise ValueError('Repair case must bind every Extraction Engine outcome')
        if len(by_prompt) != len(prompts) or set(by_prompt) != {self.scope_prompt_id, self.value_prompt_id}:
            raise ValueError('Repair case must bind exactly its scope and value prompts')
        scope, values = by_prompt[self.scope_prompt_id], by_prompt[self.value_prompt_id]
        if (any(prompt.module_id != self.module_id for prompt in prompts)
                or scope.outcome_id != 'extraction_engine.field_semantics'
                or scope.phase != 'before_execution' or scope.execution_choice is None
                or values.outcome_id != 'extraction_engine.quality_repair'
                or values.phase != 'after_execution'
                or set(values.required_fields) != {item.field for item in self.expectations}):
            raise ValueError('Repair decisions must authorize scope and check every revised value')

    def verify_source(self, pdf_bytes, page_texts):
        """Authoring check only; text presence is not learner source verification."""
        if hashlib.sha256(pdf_bytes).hexdigest() != self.source_sha256:
            raise ValueError('Repair case source bytes changed')
        for expectation in self.expectations:
            for anchor in expectation.anchors:
                if (anchor.page > len(page_texts)
                        or ' '.join(anchor.quote.split()) not in ' '.join(page_texts[anchor.page - 1].split())):
                    raise ValueError('A repair expectation has an unavailable source anchor')

    def public_definition(self):
        """Task and deliberately flawed specimen only; no expected answers."""
        return {**self.model_dump(mode='json', exclude={'expectations'}), 'case_sha256': self.digest}

    def verify_exercise(self, exercise):
        if (exercise.get('documents') != [self.source_filename]
                or exercise.get('assessment_case_id') != self.id
                or exercise.get('repair_case_sha256') != self.digest
                or exercise.get('assessment_method') != 'owned_nih_repair'
                or exercise.get('expected_fields') != [item.field for item in self.expectations]
                or exercise.get('expected_values') != {} or exercise.get('star_criteria') != {}):
            raise ValueError('The exercise must describe the pinned repair task without legacy count credit or answer keys')


def load_repair_case(package, module_id):
    path = f'repair-cases/{module_id}.json'
    if path not in package.manifest.artifacts:
        return None
    from .learner_decisions import load_prompt
    from .outcomes import package_outcomes
    try:
        case = ExtractionRepairCase.model_validate(package.json(path))
        exercise = package.json('exercises.json')[module_id]
        case.verify_exercise(exercise)
        if (case.module_id != module_id
                or package.manifest.artifacts['documents/' + case.source_filename] != case.source_sha256):
            raise ValueError('Repair case must use the exact packaged assigned source')
        prompts = [load_prompt(package, module_id, item['id'])
                   for item in package.json(f'decisions/{module_id}.json')]
        case.verify_contract(package_outcomes(package), prompts)
        return case
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CourseCatalogError('The packaged Extraction Engine repair case is invalid') from exc


def capture_repair_case(package, snapshot):
    """Bind the public authored baseline to these exact inputs, not a fake run."""
    case = load_repair_case(package, snapshot['module_id'])
    if case is None:
        return None
    documents = snapshot['documents']
    if (len(documents) != 1 or documents[0]['assigned_filename'] != case.source_filename
            or documents[0]['source_sha256'] != case.source_sha256
            or encode(snapshot['artifact'])[1] != snapshot['artifact_sha256']):
        raise CourseCatalogError('The repair case does not bind the captured assigned inputs')
    return {'case': case.public_definition(), 'input_snapshot_id': snapshot['uuid'],
            'input_snapshot_sha256': encode(snapshot)[1], 'artifact_sha256': snapshot['artifact_sha256'],
            'source_document_id': documents[0]['document_id']}


def repair_reference_matches(captured, reference):
    return reference == (encode(captured)[1] if captured is not None else None)

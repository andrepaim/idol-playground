"""Stage transitions only: no command execution, process ownership or GPU claims."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
import tempfile

from character_contracts import DEPENDENCIES, fingerprint, invalidate
from character_store import CommitUncertain, RevisionConflict

RESERVED = {'_execution.json', '_validation.json'}


class StageBlocked(ValueError):
    pass


class StageBusy(ValueError):
    pass


class StaleClaim(ValueError):
    pass


class StageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Decision:
    outcome: str
    details: dict

    def __post_init__(self):
        if self.outcome not in ('accept', 'review', 'reject') or not isinstance(self.details, dict):
            raise ValueError('Validation must accept, request review, or reject with JSON details.')
        fingerprint('input', {}, self.details, {'validator':'receipt-v1'})
        if len(json.dumps(self.details, allow_nan=False).encode()) > 64 * 1024:
            raise ValueError('Validation receipt is too large.')
        object.__setattr__(self, 'details', deepcopy(self.details))


@dataclass(frozen=True)
class Claim:
    identifier: str
    stage: str
    attempt: int
    fingerprint: str
    external_inputs: tuple
    execution: tuple = ()
    cached: bool = False
    outputs: tuple = ()


class StageCoordinator:
    def __init__(self, store):
        self.store = store

    def _receipt(self, identifier, stage, attempt, name, value):
        with tempfile.TemporaryDirectory(prefix='idol-stage-receipt-') as directory:
            source = Path(directory) / name
            value = {**value, 'recorded_at': datetime.now(timezone.utc).isoformat()}
            source.write_text(json.dumps(value, sort_keys=True, allow_nan=False))
            return self.store.publish_artifacts(identifier, stage, attempt, source.parent, [name])[0]

    def start(self, identifier, stage, parameters, versions, input_names, *, external_inputs=None):
        if not isinstance(stage, str) or stage not in DEPENDENCIES or not versions:
            raise ValueError('Choose a known stage and explicit adapter/model versions.')
        parameters, versions, input_names = deepcopy(parameters), deepcopy(versions), deepcopy(input_names)
        if external_inputs is not None and not isinstance(external_inputs, dict):
            raise ValueError('Original input hashes must be a named mapping.')
        record = self.store.load(identifier)
        if record is None:
            raise StageBlocked('Character does not exist.')
        dependencies = DEPENDENCIES[stage]
        if not isinstance(input_names, dict) or set(input_names) != set(dependencies):
            raise ValueError('Declare named inputs for every stage dependency.')
        inputs = {}
        for dependency in dependencies:
            source = record['stages'][dependency]
            if not self.store.reusable(identifier, source, source['fingerprint']):
                raise StageBlocked('A dependency is incomplete or its artifacts failed verification.')
            names = input_names[dependency]
            if (not isinstance(names, (list, tuple)) or not names or not all(isinstance(name, str) for name in names)
                    or len(set(names)) != len(names) or RESERVED.intersection(names)):
                raise ValueError('Choose unique material artifact names, not coordinator receipts.')
            for name in names:
                matches = [a for a in source['outputs'] if PurePosixPath(a['path']).name == name]
                if len(matches) != 1:
                    raise ValueError('Named dependency artifact is missing or ambiguous.')
                inputs[f'{dependency}:{name}'] = matches[0]['sha256']
        external_inputs = {} if external_inputs is None else deepcopy(external_inputs)
        if (stage == 'input' and not external_inputs) or (stage != 'input' and external_inputs):
            raise ValueError('Only input stages accept explicit original-upload hashes, and must provide them.')
        # The contract function checks input hashes, finite JSON and versions.
        expected = fingerprint(stage, {**inputs, **external_inputs}, parameters, versions)
        current = record['stages'][stage]
        if self.store.reusable(identifier, current, expected):
            return Claim(identifier, stage, current['attempt'], expected, tuple(sorted(external_inputs.items())),
                         cached=True, outputs=tuple(deepcopy(current['outputs'])))
        if any(item['state'] == 'running' for item in record['stages'].values()):
            raise StageBusy('A stage already owns this character; stop/reconcile it before changing work.')
        updated = invalidate(record, stage)
        attempt = current['attempt'] + 1
        receipt = self._receipt(identifier, stage, attempt, '_execution.json', {
            'stage':stage, 'attempt':attempt, 'fingerprint':expected, 'inputs':inputs,
            'external_inputs':external_inputs, 'parameters':parameters, 'versions':versions,
        })
        updated['stages'][stage].update(state='running', attempt=attempt, fingerprint=expected,
                                        validation_passed=False, outputs=[*current['outputs'], receipt])
        self.store.save(updated, expected_revision=record['revision'])
        execution = (receipt['path'], receipt['sha256'], receipt['bytes'])
        return Claim(identifier, stage, attempt, expected, tuple(sorted(external_inputs.items())), execution)

    def _owned(self, claim):
        record = self.store.load(claim.identifier)
        stage = record['stages'][claim.stage] if record else None
        if (claim.cached or not stage or stage['state'] != 'running' or stage['attempt'] != claim.attempt
                or stage['fingerprint'] != claim.fingerprint):
            raise StaleClaim('Stage claim was superseded; no result may replace the current revision.')
        return record

    def finish(self, claim, source_dir, names, validator):
        self._owned(claim)
        if RESERVED.intersection(names):
            raise ValueError('Worker outputs must not use coordinator receipt names.')
        outputs = self.store.publish_artifacts(claim.identifier, claim.stage, claim.attempt, source_dir, names)
        try:
            if not {value for _, value in claim.external_inputs}.issubset({a['sha256'] for a in outputs}):
                raise StageValidationError('Original upload hash does not match the published input.')
            paths = {PurePosixPath(item['path']).name: self.store.root / claim.identifier / item['path'] for item in outputs}
            decision = validator(paths)
            if not isinstance(decision, Decision):
                raise StageValidationError('Validator must return an explicit validation decision.')
            receipt = self._receipt(claim.identifier, claim.stage, claim.attempt, '_validation.json', {
                'stage':claim.stage, 'attempt':claim.attempt, 'fingerprint':claim.fingerprint,
                'outcome':decision.outcome, 'details':decision.details,
                'outputs':{name:item['sha256'] for name,item in zip(names, outputs)},
            })
            record = self._owned(claim)
            revision = record['revision']
            state = {'accept':'succeeded', 'review':'awaiting_review', 'reject':'failed'}[decision.outcome]
            execution = dict(zip(('path','sha256','bytes'), claim.execution))
            record['stages'][claim.stage].update(state=state, validation_passed=decision.outcome == 'accept',
                                                 outputs=[*outputs, execution, receipt])
            record['revision'] += 1
            self.store.save(record, expected_revision=revision)
            return record
        except CommitUncertain:
            raise  # never mask uncertain publication with a blind failure write
        except RevisionConflict as error:
            raise StaleClaim('Character changed during completion.') from error
        except StaleClaim:
            raise
        except Exception as error:
            self.end(claim, 'failed', 'validation_error')
            raise StageValidationError('Published snapshot failed validation or integrity checks.') from error

    def end(self, claim, state, reason_code):
        """Trusted process layer calls only after its worker has stopped/reaped."""
        if state not in ('failed', 'cancelled', 'interrupted') or not isinstance(reason_code, str) or not re.fullmatch('[a-zA-Z0-9_-]{1,64}', reason_code):
            raise ValueError('Use an explicit failure/end state and safe reason code.')
        record = self._owned(claim)
        receipt = self._receipt(claim.identifier, claim.stage, claim.attempt, '_validation.json', {
            'stage':claim.stage, 'attempt':claim.attempt, 'fingerprint':claim.fingerprint, 'outcome':state, 'code':reason_code,
        })
        # Receipt publication takes time: reread ownership/revision before CAS.
        record = self._owned(claim)
        revision = record['revision']
        record['stages'][claim.stage].update(state=state, validation_passed=False,
                                             outputs=[*record['stages'][claim.stage]['outputs'], receipt])
        record['revision'] += 1
        try:
            self.store.save(record, expected_revision=revision)
        except RevisionConflict as error:
            raise StaleClaim('Character changed during the end transition.') from error
        return record

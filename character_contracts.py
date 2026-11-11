"""Private job contracts and dependency logic, deliberately separate from execution.

This module never reads/writes artifacts, starts workers, or changes legacy jobs.
A valid succeeded record is not proof its output bytes still match their hashes.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math
import re

DEPENDENCIES = {
    'input': (),
    'assessment': ('input',),
    'splat': ('input',),
    'mesh': ('splat',),
    'mesh_assessment': ('mesh', 'assessment'),
    'prepare': ('mesh', 'mesh_assessment'),
    'skeleton': ('prepare',),
    'mapping': ('skeleton', 'mesh_assessment'),
    'skin': ('skeleton', 'prepare'),
    'motion': ('mapping', 'skin'),
    'package': ('motion',),
}
STATES = {'pending', 'running', 'awaiting_review', 'succeeded', 'failed', 'cancelled', 'interrupted', 'blocked'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _integer(value):
    return type(value) is int and value >= 0


def _json(value):
    if isinstance(value, dict):
        _require(all(isinstance(key, str) for key in value), 'JSON object keys must be strings.')
        for item in value.values():
            _json(item)
    elif isinstance(value, list):
        for item in value:
            _json(item)
    else:
        _require(value is None or type(value) in (str, bool, int, float), 'Unsupported JSON value.')
        if isinstance(value, float):
            _require(math.isfinite(value), 'Nonfinite JSON number.')


def new_character(identifier):
    record = {'schema_version': 1, 'id': identifier, 'revision': 0, 'stages': {
        name: {'state': 'pending', 'attempt': 0, 'fingerprint': None, 'validation_passed': False, 'outputs': []}
        for name in DEPENDENCIES
    }}
    return validate_character(record)


def validate_character(record):
    _require(isinstance(record, dict) and set(record) == {'schema_version', 'id', 'revision', 'stages'}, 'Unknown or missing character fields.')
    _require(type(record['schema_version']) is int and record['schema_version'] == 1, 'Unsupported character schema version.')
    _require(isinstance(record['id'], str) and re.fullmatch('[0-9a-f]{32}', record['id']) is not None, 'Invalid character identity.')
    _require(_integer(record['revision']), 'Invalid character revision.')
    stages = record['stages']
    _require(isinstance(stages, dict) and set(stages) == set(DEPENDENCIES), 'Missing or unsupported character stages.')
    for stage in stages.values():
        _require(isinstance(stage, dict) and set(stage) == {'state', 'attempt', 'fingerprint', 'validation_passed', 'outputs'}, 'Unknown or missing stage fields.')
        _require(isinstance(stage['state'], str) and stage['state'] in STATES, 'Unsupported stage state.')
        _require(_integer(stage['attempt']), 'Invalid stage attempt.')
        _require(stage['fingerprint'] is None or _hash(stage['fingerprint']), 'Invalid stage fingerprint.')
        _require(type(stage['validation_passed']) is bool, 'Invalid validation result.')
        _require(isinstance(stage['outputs'], list), 'Invalid stage outputs.')
        for artifact in stage['outputs']:
            _require(isinstance(artifact, dict) and set(artifact) == {'path', 'sha256', 'bytes'}, 'Invalid artifact fields.')
            path = artifact['path']
            _require(isinstance(path, str) and re.fullmatch('[a-zA-Z0-9_./-]+', path) is not None
                     and all(part not in ('', '.', '..') for part in path.split('/')), 'Unsafe relative artifact path.')
            _require(_hash(artifact['sha256']) and _integer(artifact['bytes']), 'Invalid artifact hash or byte count.')
        if stage['state'] == 'succeeded':
            _require(stage['validation_passed'] and _hash(stage['fingerprint']) and bool(stage['outputs']), 'Successful stages require validated, fingerprinted output artifacts.')
    return deepcopy(record)


def fingerprint(stage, inputs, parameters, versions):
    _require(isinstance(stage, str) and stage in DEPENDENCIES, 'Unknown stage.')
    _require(isinstance(inputs, dict) and all(isinstance(key, str) and bool(key) and _hash(value) for key, value in inputs.items()), 'Invalid input artifact hashes.')
    _require(isinstance(versions, dict) and all(isinstance(key, str) and bool(key) and isinstance(value, str) and bool(value) for key, value in versions.items()), 'Invalid tool/model versions.')
    _require(isinstance(parameters, dict), 'Parameters must be a JSON object.')
    _json(parameters)
    payload = {'contract_version': 1, 'stage': stage, 'inputs': inputs, 'parameters': parameters, 'versions': versions}
    return sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def affected_stages(changed):
    _require(isinstance(changed, str) and changed in DEPENDENCIES, 'Unknown stage.')
    result = {changed}
    while True:
        expanded = result | {name for name, dependencies in DEPENDENCIES.items() if result.intersection(dependencies)}
        if expanded == result:
            return result
        result = expanded


def invalidate(record, changed):
    revised = validate_character(record)
    for name in affected_stages(changed):
        revised['stages'][name].update(state='pending', validation_passed=False, fingerprint=None)
    revised['revision'] += 1
    # Old artifact references are retained; pending outputs must never be reused
    # without an execution fingerprint and byte-level verification by the store.
    return validate_character(revised)

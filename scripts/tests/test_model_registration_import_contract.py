"""#367 front-end handoff example and registration contract boundaries."""
import copy
import json
from pathlib import Path
import unittest

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]

class RegistrationImportContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        api = yaml.safe_load((ROOT / 'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
        cls.validator = Draft202012Validator({'$ref': '#/components/schemas/RegisterModelVersion', 'components': api['components']})
        cls.example = json.loads((ROOT / 'contracts/examples/model-registration-import.json').read_text(encoding='utf-8'))

    def test_import_example_and_old_manual_request(self):
        self.validator.validate(self.example)
        manual = copy.deepcopy(self.example)
        manual.pop('registration')
        manual['evaluation'].pop('limitations')
        self.validator.validate(manual)
        manual['kind'] = 'PROMPT'
        manual.pop('artifactUri')
        self.validator.validate(manual)

    def test_model_requires_uri_and_approval_is_not_registration(self):
        for value in (None, '', ' '):
            request = copy.deepcopy(self.example)
            request['artifactUri'] = value
            self.assertTrue(list(self.validator.iter_errors(request)))
        for field in ('approved', 'approvedBy', 'scopes', 'reason', 'reanalysisPlanned'):
            request = copy.deepcopy(self.example)
            request[field] = True
            self.assertTrue(list(self.validator.iter_errors(request)))

    def test_provenance_and_limitations_constraints(self):
        for changes in ({'source': 'MANUAL'}, {'jsonSha256': None}, {'jsonSha256': 'bad'},
                        {'manifestSha256': None}, {'modifiedFields': ['approvedBy']},
                        {'modifiedFields': ['artifactUri', 'artifactUri']}):
            request = copy.deepcopy(self.example)
            request['registration'].update(changes)
            self.assertTrue(list(self.validator.iter_errors(request)), changes)
        for value in ([None], [' '], ['x' * 4001]):
            request = copy.deepcopy(self.example)
            request['evaluation']['limitations'] = value
            self.assertTrue(list(self.validator.iter_errors(request)))

    def test_manifest_is_optional_but_paths_are_relative(self):
        request = copy.deepcopy(self.example)
        request['registration'].pop('manifestSha256')
        request['registration']['artifactFiles'] = []
        self.validator.validate(request)
        for path in ('../config.json', '/config.json', 'a/../config.json', 'a//b', 'C:/config.json'):
            request = copy.deepcopy(self.example)
            request['registration']['artifactFiles'][0]['file'] = path
            self.assertTrue(list(self.validator.iter_errors(request)), path)

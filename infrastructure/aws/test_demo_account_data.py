import datetime as dt
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import demo_account_data as demo


class DemoChildrenTest(unittest.TestCase):
    def test_new_fifth_grader_and_existing_birth_year(self):
        class Clock(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 11, 28, tzinfo=tz)

        class Api:
            writes = []

            def parent(self):
                return 'synthetic-token', None

            def children(self, token):
                return {'기존': {'id': 'existing', 'grade': 5, 'birthYear': 2014}}

            def call(self, method, path, body=None, token=None):
                if method == 'POST':
                    self.writes.append((path, body))
                return 200, {'items': [], 'nextAction': 'READY'}, None

            def ok(self, label, status, payload, accepted):
                return payload

        api = Api()
        with patch.object(demo.dt, 'datetime', Clock):
            demo.cmd_children(api, SimpleNamespace(child=['신규:5', '기존:5']))
        self.assertEqual(len(api.writes), 1)
        self.assertEqual(api.writes[0][0], '/children')
        self.assertEqual(api.writes[0][1]['birthYear'], 2015)
        self.assertEqual(api.writes[0][1]['grade'], 5)


if __name__ == '__main__':
    unittest.main()

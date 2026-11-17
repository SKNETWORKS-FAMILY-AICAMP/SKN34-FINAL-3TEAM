"""#723: 본인 배치·친구 방의 면별 격자 계약을 같은 경계값으로 검증한다."""
from pathlib import Path
import unittest

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


class RoomDecorContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        cls.schemas = cls.spec["components"]["schemas"]

    def variants(self, cell):
        return [
            (self.schemas["RoomDecorSpotInput"], {**cell, "itemKey": "POT"}),
            (self.schemas["RoomDecorSpot"], {**cell, "itemKey": "POT", "name": "화분", "assetKey": "room/pot"}),
            (self.schemas["FriendRoom"]["properties"]["room"]["properties"]["decor"]["items"],
             {**cell, "assetKey": "room/pot"}),
        ]

    def test_all_public_shapes_enforce_each_surface_boundary(self):
        for surface, max_col, max_row in [("FLOOR", 16, 12), ("WALL_BACK", 15, 5), ("WALL_LEFT", 10, 5)]:
            for col, row, valid in [(0, 0, True), (max_col, max_row, True),
                                    (-1, 0, False), (0, -1, False),
                                    (max_col + 1, 0, False), (0, max_row + 1, False)]:
                for schema, body in self.variants(dict(surface=surface, col=col, row=row)):
                    with self.subTest(body=body):
                        self.assertEqual(valid, Draft202012Validator(schema).is_valid(body))

    def test_missing_null_fractional_unknown_and_old_cells_are_rejected(self):
        cell = dict(surface="FLOOR", col=0, row=0)
        invalid = [dict(surface="WALL_RIGHT", col=0, row=0), dict(surface="floor", col=0, row=0),
                   dict(surface="FLOOR", col=0.5, row=0), dict(spotNo=1)]
        invalid += [{k: v for k, v in cell.items() if k != key} for key in cell]
        invalid += [{**cell, key: None} for key in cell]
        for value in invalid:
            for schema, body in self.variants(value):
                with self.subTest(body=body):
                    self.assertFalse(Draft202012Validator(schema).is_valid(body))

    def test_request_and_both_responses_limit_placements_to_eight(self):
        request = self.spec["paths"]["/students/me/room/decor-spots"]["put"]["requestBody"]["content"]["application/json"]["schema"]
        response = self.schemas["RoomDecorSpots"]
        friend = self.schemas["FriendRoom"]["properties"]["room"]["properties"]["decor"]
        shapes = self.variants(dict(surface="FLOOR", col=0, row=0))
        for schema, (_, item), wrap in [(request, shapes[0], True), (response, shapes[1], True), (friend, shapes[2], False)]:
            validator = Draft202012Validator({**schema, "components": self.spec["components"]})
            for count in (0, 8, 9):
                body = [dict(item, col=i) for i in range(count)]
                self.assertEqual(count <= 8, validator.is_valid({"spots": body} if wrap else body))


if __name__ == "__main__":
    unittest.main()

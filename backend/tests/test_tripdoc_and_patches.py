import unittest
from datetime import date, datetime, timezone

import os
import sys

# Ensure `backend/` is on sys.path so `import app.*` works when running tests from repo root.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.tripsync.json_patch import apply_json_patch, JsonPatchError
from app.tripsync.tripdoc_validators import (
    normalize_tripdoc_dates,
    validate_patch_paths,
    validate_tripdoc_invariants,
)
from app.tripsync.timezone import coerce_to_utc, ensure_end_not_before_start


class TestJsonPatch(unittest.TestCase):
    def test_apply_patch_add_replace_remove(self):
        doc = {"a": {"b": [1, 2]}}
        apply_json_patch(doc, [{"op": "add", "path": "/a/b/-", "value": 3}])
        self.assertEqual(doc["a"]["b"], [1, 2, 3])
        apply_json_patch(doc, [{"op": "replace", "path": "/a/b/0", "value": 9}])
        self.assertEqual(doc["a"]["b"][0], 9)
        apply_json_patch(doc, [{"op": "remove", "path": "/a/b/1"}])
        self.assertEqual(doc["a"]["b"], [9, 3])

    def test_rejects_bad_path(self):
        with self.assertRaises(JsonPatchError):
            apply_json_patch({"a": 1}, [{"op": "replace", "path": "a", "value": 2}])


class TestTripDocValidation(unittest.TestCase):
    def test_validate_patch_paths_restricts(self):
        allowed = {"/title", "/members"}
        validate_patch_paths([{"op": "replace", "path": "/title", "value": "x"}], allowed)
        with self.assertRaises(ValueError):
            validate_patch_paths([{"op": "replace", "path": "/trip", "value": "x"}], allowed)

    def test_tripdoc_invariants_accepts_iso_dates(self):
        doc = {
            "members": [
                {
                    "member_id": "m1",
                    "display_name": "A",
                    "travel_segments": [
                        {
                            "arrival": {"date": "2026-01-10", "city": "X"},
                            "departure": {"date": "2026-01-12", "city": "X"},
                            "lodging_stay": {"lodging_id": "lodg1", "from_night": "2026-01-10", "to_night_exclusive": "2026-01-12"},
                        }
                    ],
                }
            ],
            "lodgings": [
                {
                    "lodging_id": "lodg1",
                    "name": "H",
                    "booking_nights": {"check_in_date": "2026-01-10", "check_out_date": "2026-01-12", "nights": 2},
                }
            ],
        }
        normalize_tripdoc_dates(doc)
        validate_tripdoc_invariants(doc, allowed_member_ids={"m1"})

    def test_tripdoc_invariants_rejects_bad_nights_math(self):
        doc = {
            "members": [{"member_id": "m1", "display_name": "A", "travel_segments": []}],
            "lodgings": [
                {
                    "lodging_id": "lodg1",
                    "name": "H",
                    "booking_nights": {"check_in_date": "2026-01-10", "check_out_date": "2026-01-12", "nights": 3},
                }
            ],
        }
        normalize_tripdoc_dates(doc)
        with self.assertRaises(ValueError):
            validate_tripdoc_invariants(doc, allowed_member_ids={"m1"})


class TestTimezoneContract(unittest.TestCase):
    def test_coerce_to_utc_makes_aware(self):
        naive = datetime(2026, 1, 1, 10, 0, 0)
        out = coerce_to_utc(naive, assume_tz="UTC")
        self.assertIsNotNone(out.tzinfo)
        self.assertEqual(out.tzinfo, timezone.utc)

    def test_end_not_before_start(self):
        start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            ensure_end_not_before_start(start, end)


if __name__ == "__main__":
    unittest.main()



import unittest

import os
import sys

# Ensure `backend/` is on sys.path so `import app.*` works when running tests from repo root.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.tripsync.balance_math import apply_settlement


import unittest
from types import SimpleNamespace
import os
import sys

# Ensure `backend/` is on sys.path so `import app.*` works when running tests from repo root.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import HTTPException
from app.tripsync.balance_math import apply_settlement
from app.tripsync.service import TripService


def _make_trip(members: list[tuple[str, str]]):
    return SimpleNamespace(
        members=[
            SimpleNamespace(member_id=mid, display_name=name, user=None)
            for mid, name in members
        ]
    )


class TestBalanceMath(unittest.TestCase):
    def test_apply_settlement_moves_balances_toward_zero(self):
        # A owes B 50
        balances = {"A": -50.0, "B": 50.0}
        apply_settlement(balances, payer_member_id="A", payee_member_id="B", amount=50.0)
        self.assertAlmostEqual(balances["A"], 0.0)
        self.assertAlmostEqual(balances["B"], 0.0)

    def test_apply_settlement_rejects_non_positive_amount(self):
        balances = {"A": 0.0, "B": 0.0}
        with self.assertRaises(ValueError):
            apply_settlement(balances, payer_member_id="A", payee_member_id="B", amount=0.0)

    def test_apply_settlement_rejects_same_party(self):
        balances = {"A": 0.0}
        with self.assertRaises(ValueError):
            apply_settlement(balances, payer_member_id="A", payee_member_id="A", amount=10.0)


class TestCustomAndEqualSplits(unittest.TestCase):
    def test_equal_and_exact_splits_and_settlement_workflow(self):
        """
        Ported from test_custom_split_remote.sh / test_custom_split_local.sh:
        1. Equal split expense: 300 paid by Sahil, split among Sahil, Bob, Charlie -> Sahil +200, Bob -100, Charlie -100
        2. Exact split expense: 200 paid by Bob, custom splits Sahil=50, Bob=50, Charlie=100 -> Sahil +150, Bob +50, Charlie -200
        3. Settlement: Charlie pays Sahil 100 -> Sahil +50, Bob +50, Charlie -100
        """
        trip = _make_trip([("m_sahil", "Sahil"), ("m_bob", "Bob"), ("m_charlie", "Charlie")])

        expenses = [
            SimpleNamespace(
                amount=300.0,
                paid_by_member_id="m_sahil",
                split_type="equal",
                split_with_member_ids=["m_sahil", "m_bob", "m_charlie"],
                custom_splits=[],
            ),
            SimpleNamespace(
                amount=200.0,
                paid_by_member_id="m_bob",
                split_type="exact",
                split_with_member_ids=[],
                custom_splits=[
                    {"member_id": "m_sahil", "amount": 50.0},
                    {"member_id": "m_bob", "amount": 50.0},
                    {"member_id": "m_charlie", "amount": 100.0},
                ],
            ),
        ]
        settlements = [
            SimpleNamespace(
                payer_member_id="m_charlie",
                payee_member_id="m_sahil",
                amount=100.0,
                mode="upi",
            )
        ]

        balances = {
            b.member_id: b
            for b in TripService._compute_balances_from_records(trip, expenses, settlements)
        }
        self.assertAlmostEqual(balances["m_sahil"].balance, 50.0)
        self.assertAlmostEqual(balances["m_bob"].balance, 50.0)
        self.assertAlmostEqual(balances["m_charlie"].balance, -100.0)
        self.assertEqual(balances["m_sahil"].display_name, "Sahil")

    def test_validate_expense_deduplicates_equal_split_and_rejects_duplicate_custom_splits(self):
        trip = _make_trip([("m1", "Alice"), ("m2", "Bob")])

        deduped = TripService._validate_expense(
            trip=trip,
            amount=100.0,
            paid_by_member_id="m1",
            split_type="equal",
            split_with_member_ids=["m1", "m1", "m2"],
            custom_splits=[],
        )
        self.assertEqual(deduped, ["m1", "m2"])

        with self.assertRaises(HTTPException) as ctx:
            TripService._validate_expense(
                trip=trip,
                amount=100.0,
                paid_by_member_id="m1",
                split_type="exact",
                split_with_member_ids=[],
                custom_splits=[
                    {"member_id": "m1", "amount": 50.0},
                    {"member_id": "m1", "amount": 50.0},
                ],
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Duplicate member_id", ctx.exception.detail)

    def test_compute_balances_deduplicates_legacy_equal_split_and_labels_former_member(self):
        trip = _make_trip([("m1", "Alice"), ("m2", "Bob")])
        expenses = [
            SimpleNamespace(
                amount=100.0,
                paid_by_member_id="m1",
                split_type="equal",
                split_with_member_ids=["m1", "m1", "m2"],
                custom_splits=[],
            ),
            SimpleNamespace(
                amount=60.0,
                paid_by_member_id="m_removed",
                split_type="equal",
                split_with_member_ids=["m1", "m2"],
                custom_splits=[],
            ),
        ]
        entries = {
            b.member_id: b
            for b in TripService._compute_balances_from_records(trip, expenses, [])
        }
        # Expense 1: m1 +50, m2 -50; Expense 2: m_removed +60, m1 -30, m2 -30
        self.assertAlmostEqual(entries["m1"].balance, 20.0)
        self.assertAlmostEqual(entries["m2"].balance, -80.0)
        self.assertAlmostEqual(entries["m_removed"].balance, 60.0)
        self.assertEqual(entries["m_removed"].display_name, "Former Member")

    def test_validate_member_removal_guards_referenced_members(self):
        trip = _make_trip([("m1", "Alice"), ("m2", "Bob"), ("m3", "Charlie")])
        expenses = [
            SimpleNamespace(
                amount=100.0,
                paid_by_member_id="m1",
                split_type="equal",
                split_with_member_ids=["m1", "m2"],
                custom_splits=[],
            )
        ]
        # m3 is not referenced -> allowed
        TripService._validate_member_removal(trip, "m3", expenses, [])

        # m2 is in split_with_member_ids -> rejected
        with self.assertRaises(HTTPException) as ctx:
            TripService._validate_member_removal(trip, "m2", expenses, [])
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()



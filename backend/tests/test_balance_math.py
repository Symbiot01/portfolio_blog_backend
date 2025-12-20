import unittest

from app.tripsync.balance_math import apply_settlement


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



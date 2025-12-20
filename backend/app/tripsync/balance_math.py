from __future__ import annotations

import math
from typing import MutableMapping


def apply_settlement(
    balance_map: MutableMapping[str, float],
    payer_member_id: str,
    payee_member_id: str,
    amount: float,
) -> None:
    """
    Apply a settlement payment to balances.

    Balance convention:
    - positive means others owe them (creditor)
    - negative means they owe others (debtor)

    If payer pays payee, both should move toward 0:
    - payer's balance increases by amount
    - payee's balance decreases by amount
    """
    if payer_member_id == payee_member_id:
        raise ValueError("payer_member_id and payee_member_id must be different")
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("amount must be a finite positive number")

    balance_map[payer_member_id] = balance_map.get(payer_member_id, 0.0) + amount
    balance_map[payee_member_id] = balance_map.get(payee_member_id, 0.0) - amount



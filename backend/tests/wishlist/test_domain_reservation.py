"""Domain reservation same_actor helper tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.wishlist.domain.reservation import Reservation, ReservationStatus


def test_same_actor_user_and_guest():
    r = Reservation(
        id="r1",
        product_id="p1",
        group_id="g1",
        status=ReservationStatus.ACTIVE,
        expires_at=datetime.utcnow() + timedelta(days=14),
        reserved_as_name="Maya",
        actor_user_id=None,
        guest_id="g-abc",
    )
    assert r.same_actor(guest_id="g-abc")
    assert not r.same_actor(guest_id="other")
    assert not r.same_actor(user_id="u1")

    r.actor_user_id = "u1"
    assert r.same_actor(user_id="u1")
    assert r.same_actor(guest_id="g-abc")  # guest id still matches

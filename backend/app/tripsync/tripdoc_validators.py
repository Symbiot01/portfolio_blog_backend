from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable, Optional, Set


def _coerce_date(v: Any) -> date:
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        # ISO date: YYYY-MM-DD
        return date.fromisoformat(v)
    raise ValueError("expected date")


def normalize_tripdoc_dates(tripdoc: Dict[str, Any]) -> None:
    """
    Mutates tripdoc dict in-place converting ISO date strings into `date` objects
    for known date fields used by TripDoc.
    """
    dr = tripdoc.get("date_range")
    if isinstance(dr, dict):
        if dr.get("start") is not None:
            dr["start"] = _coerce_date(dr["start"])
        if dr.get("end") is not None:
            dr["end"] = _coerce_date(dr["end"])

    members = tripdoc.get("members") or []
    if isinstance(members, list):
        for m in members:
            if not isinstance(m, dict):
                continue
            segs = m.get("travel_segments") or []
            if not isinstance(segs, list):
                continue
            for s in segs:
                if not isinstance(s, dict):
                    continue
                arrival = s.get("arrival")
                if isinstance(arrival, dict) and arrival.get("date") is not None:
                    arrival["date"] = _coerce_date(arrival["date"])
                departure = s.get("departure")
                if isinstance(departure, dict) and departure.get("date") is not None:
                    departure["date"] = _coerce_date(departure["date"])
                lodging_stay = s.get("lodging_stay")
                if isinstance(lodging_stay, dict):
                    if lodging_stay.get("from_night") is not None:
                        lodging_stay["from_night"] = _coerce_date(lodging_stay["from_night"])
                    if lodging_stay.get("to_night_exclusive") is not None:
                        lodging_stay["to_night_exclusive"] = _coerce_date(lodging_stay["to_night_exclusive"])

    lodgings = tripdoc.get("lodgings") or []
    if isinstance(lodgings, list):
        for l in lodgings:
            if not isinstance(l, dict):
                continue
            bn = l.get("booking_nights")
            if isinstance(bn, dict):
                if bn.get("check_in_date") is not None:
                    bn["check_in_date"] = _coerce_date(bn["check_in_date"])
                if bn.get("check_out_date") is not None:
                    bn["check_out_date"] = _coerce_date(bn["check_out_date"])


def _days_between(start: date, end_exclusive: date) -> int:
    return (end_exclusive - start).days


def validate_tripdoc_invariants(tripdoc: Dict[str, Any], allowed_member_ids: Set[str]) -> None:
    """
    Validates core invariants for TripDoc payload after patch application.
    Raises ValueError with a human-readable message on failure.
    """
    members = tripdoc.get("members") or []
    if not isinstance(members, list):
        raise ValueError("members must be a list")

    for m in members:
        if not isinstance(m, dict):
            raise ValueError("members items must be objects")
        mid = str(m.get("member_id") or "")
        if not mid or mid not in allowed_member_ids:
            raise ValueError("member_id must match an existing trip member")

        segs = m.get("travel_segments") or []
        if not isinstance(segs, list):
            raise ValueError("travel_segments must be a list")
        for s in segs:
            if not isinstance(s, dict):
                raise ValueError("travel_segments items must be objects")
            arrival = s.get("arrival") or {}
            departure = s.get("departure") or {}
            if not isinstance(arrival, dict) or not isinstance(departure, dict):
                raise ValueError("arrival/departure must be objects")
            a_date = arrival.get("date")
            d_date = departure.get("date")
            if not isinstance(a_date, date) or not isinstance(d_date, date):
                raise ValueError("arrival.date and departure.date must be dates (YYYY-MM-DD)")
            if d_date < a_date:
                raise ValueError("departure.date must be >= arrival.date")

            lodging_stay = s.get("lodging_stay")
            if lodging_stay is not None:
                if not isinstance(lodging_stay, dict):
                    raise ValueError("lodging_stay must be an object")
                from_night = lodging_stay.get("from_night")
                to_night_excl = lodging_stay.get("to_night_exclusive")
                if not isinstance(from_night, date) or not isinstance(to_night_excl, date):
                    raise ValueError("lodging_stay nights must be dates (YYYY-MM-DD)")
                if to_night_excl <= from_night:
                    raise ValueError("lodging_stay.to_night_exclusive must be after from_night")

    lodgings = tripdoc.get("lodgings") or []
    if not isinstance(lodgings, list):
        raise ValueError("lodgings must be a list")

    lodging_ids: Set[str] = set()
    for l in lodgings:
        if not isinstance(l, dict):
            raise ValueError("lodgings items must be objects")
        lid = str(l.get("lodging_id") or "")
        if not lid:
            raise ValueError("lodgings.lodging_id is required")
        lodging_ids.add(lid)

        bn = l.get("booking_nights") or {}
        if not isinstance(bn, dict):
            raise ValueError("booking_nights must be an object")
        ci = bn.get("check_in_date")
        co = bn.get("check_out_date")
        nights = bn.get("nights")
        if not isinstance(ci, date) or not isinstance(co, date):
            raise ValueError("booking_nights.check_in_date/check_out_date must be dates (YYYY-MM-DD)")
        if co <= ci:
            raise ValueError("booking_nights.check_out_date must be after check_in_date")
        expected = _days_between(ci, co)
        if not isinstance(nights, int) or nights != expected:
            raise ValueError("booking_nights.nights must equal (check_out_date - check_in_date) in days")

    # If segments reference a lodging_id, that lodging must exist.
    for m in members:
        for s in (m.get("travel_segments") or []):
            lodging_stay = (s or {}).get("lodging_stay")
            if lodging_stay and isinstance(lodging_stay, dict):
                lid = lodging_stay.get("lodging_id")
                if lid and str(lid) not in lodging_ids:
                    raise ValueError("lodging_stay.lodging_id must exist in lodgings")


def validate_patch_paths(patch_ops: Iterable[Dict[str, Any]], allowed_prefixes: Set[str]) -> None:
    for op in patch_ops:
        path = op.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError("patch path must be a string starting with '/'")
        ok = any(path == p or path.startswith(p + "/") for p in allowed_prefixes)
        if not ok:
            raise ValueError("patch path not allowed")



"""Utilities to relate SGA print jobs to Open-OMS orders."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Set


def normalize_item_code(value: Any) -> str:
    """Return a normalized uppercase item code string."""
    if value is None:
        return ""
    return str(value).strip().upper()


def extract_print_items(details_raw: Any) -> Set[str]:
    """Extract normalized item codes from an SGA log details payload.

    The payload is expected to be JSON with an `items` array.
    """
    details: Dict[str, Any]
    if isinstance(details_raw, dict):
        details = details_raw
    else:
        try:
            details = json.loads(details_raw or "{}")
        except Exception:
            return set()

    items = details.get("items", [])
    if not isinstance(items, list):
        return set()

    out = {normalize_item_code(i) for i in items if normalize_item_code(i)}
    return out


def extract_order_item_codes(order: Dict[str, Any]) -> Set[str]:
    """Extract normalized item codes from an order record."""
    out: Set[str] = set()
    for item in order.get("items", []) or []:
        code = (
            item.get("item_code")
            or item.get("ItemCode")
            or item.get("code")
            or item.get("item")
        )
        normalized = normalize_item_code(code)
        if normalized:
            out.add(normalized)
    return out


def find_matching_order_ids(
    print_items: Set[str],
    orders: Iterable[Dict[str, Any]],
    allowed_statuses: Optional[Set[str]] = None,
) -> List[str]:
    """Find order IDs whose item set fully contains the print item set."""
    if not print_items:
        return []

    allowed_statuses = allowed_statuses or {"Pendiente", "En Espera", "En Proceso"}

    matches: List[str] = []
    for order in orders:
        status = str(order.get("status", ""))
        if status not in allowed_statuses:
            continue

        order_id = str(order.get("order_id", "")).strip()
        if not order_id:
            continue

        order_items = extract_order_item_codes(order)
        if not order_items:
            continue

        if print_items.issubset(order_items):
            matches.append(order_id)

    return matches

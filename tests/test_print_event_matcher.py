from core.print_event_matcher import (
    extract_order_item_codes,
    extract_print_items,
    find_matching_order_ids,
)


def test_extract_print_items_json_payload():
    payload = '{"count": 2, "items": [" iff-qb001 ", "VAR-QB00078"], "method": "print_agent"}'
    items = extract_print_items(payload)
    assert items == {"IFF-QB001", "VAR-QB00078"}


def test_extract_order_item_codes_accepts_multiple_keys():
    order = {
        "items": [
            {"item_code": "AAA-1"},
            {"ItemCode": "bbb-2"},
            {"code": "CCC-3"},
        ]
    }
    assert extract_order_item_codes(order) == {"AAA-1", "BBB-2", "CCC-3"}


def test_find_matching_order_ids_unique_subset_match():
    orders = [
        {
            "order_id": "1001",
            "status": "Pendiente",
            "items": [{"item_code": "IFF-QB00063"}],
        },
        {
            "order_id": "1002",
            "status": "Enviado al cliente",
            "items": [{"item_code": "IFF-QB00063"}],
        },
    ]

    matches = find_matching_order_ids({"IFF-QB00063"}, orders)
    assert matches == ["1001"]


def test_find_matching_order_ids_ambiguous():
    orders = [
        {
            "order_id": "1001",
            "status": "Pendiente",
            "items": [{"item_code": "IFF-QB00063"}],
        },
        {
            "order_id": "1002",
            "status": "Pendiente",
            "items": [{"item_code": "IFF-QB00063"}],
        },
    ]

    matches = find_matching_order_ids({"IFF-QB00063"}, orders)
    assert matches == ["1001", "1002"]

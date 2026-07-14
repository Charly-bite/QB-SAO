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


# ---- Edge-case tests for full coverage ----


def test_normalize_item_code_none():
    from core.print_event_matcher import normalize_item_code
    assert normalize_item_code(None) == ""


def test_extract_print_items_dict_input():
    """When input is already a dict (not a string)."""
    result = extract_print_items({"items": ["ITEM-A"]})
    assert result == {"ITEM-A"}


def test_extract_print_items_invalid_json_string():
    result = extract_print_items("not valid json {{{")
    assert result == set()


def test_extract_print_items_non_list_items():
    result = extract_print_items({"items": "not a list"})
    assert result == set()


def test_extract_print_items_none_input():
    result = extract_print_items(None)
    assert result == set()


def test_find_matching_order_ids_empty_print_items():
    orders = [{"order_id": "1001", "status": "Pendiente", "items": [{"item_code": "A"}]}]
    matches = find_matching_order_ids(set(), orders)
    assert matches == []


def test_find_matching_order_ids_order_no_id():
    orders = [{"order_id": "", "status": "Pendiente", "items": [{"item_code": "A"}]}]
    matches = find_matching_order_ids({"A"}, orders)
    assert matches == []


def test_find_matching_order_ids_order_no_items():
    orders = [{"order_id": "1001", "status": "Pendiente", "items": []}]
    matches = find_matching_order_ids({"A"}, orders)
    assert matches == []


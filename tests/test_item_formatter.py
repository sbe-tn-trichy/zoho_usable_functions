from zoho_usable_functions.inventory.item_formatter import extract_group_attributes, item_to_row_dict


def test_extract_group_attributes_formats_pairs():
    item = {
        "attribute_name1": "Color",
        "attribute_option_name1": "Blue",
        "attribute_name2": "Size",
        "attribute_option_name2": "100ml",
    }
    result = extract_group_attributes(item)
    assert result == "Color=Blue; Size=100ml"


def test_item_to_row_dict_flattens_keys():
    item = {
        "item_id": "12345",
        "name": "Test Item",
        "sku": "SKU-123",
        "attribute_name1": "Color",
        "attribute_option_name1": "Red",
        "rate": 100.0,
        "purchase_rate": 80.0,
    }
    row = item_to_row_dict(item)

    assert row["item_id"] == "12345"
    assert row["name"] == "Test Item"
    assert row["sku"] == "SKU-123"
    assert row["group_attributes"] == "Color=Red"
    assert row["rate"] == 100.0
    assert row["purchase_rate"] == 80.0

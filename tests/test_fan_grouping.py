from zoho_usable_functions.inventory.fan_grouping import classify_item_type, propose_fan_group


def test_classify_item_type_by_sku():
    assert classify_item_type({"sku": "FCE123", "item_name": "Fan"}) == "Ceiling Fan"
    assert classify_item_type({"sku": "FEX123", "item_name": "Fan"}) == "Exhaust Fan"
    assert classify_item_type({"sku": "FPE123", "item_name": "Fan"}) == "Pedestal Fan"
    assert classify_item_type({"sku": "FTA123", "item_name": "Fan"}) == "Table Fan"
    assert classify_item_type({"sku": "FWA123", "item_name": "Fan"}) == "Wall Fan"


def test_propose_fan_group_pedestal():
    group_name, group_id, action = propose_fan_group("Pedestal Fan HS 400mm", "FPEH123", "Pedestal Fan")
    assert group_name == "PF HS"
    assert group_id != ""
    assert action == "Assign to Existing Group"

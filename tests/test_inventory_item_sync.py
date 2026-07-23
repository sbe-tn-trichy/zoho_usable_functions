import pandas as pd

from zoho_usable_functions.inventory.item_sync import (
    build_inventory_item_payload,
    compare_items_with_inventory,
    create_inventory_items_from_sheet,
    create_missing_inventory_items,
    fetch_inventory_items,
    fetch_items_for_purchase_account,
    fetch_items_by_status,
    find_item_diff,
    find_active_items_with_name_containing,
    items_to_frame,
    mark_inventory_items_inactive,
    normalize_sku,
    prepare_item_create_payloads,
)


class FakeItems:
    def __init__(self):
        self.list_all_params = None
        self.created = []
        self.updated = []

    def list_all(self, params=None):
        self.list_all_params = params
        return [{"item_id": "1", "sku": "ABC-1", "name": "Existing"}]

    def list_by_purchase_account(self, account_id, status="all"):
        params = {"purchase_account_id": account_id}
        if status.lower() != "all":
            params["filter_by"] = f"Status.{status.title()}"
        return self.list_all(params=params)

    def list_by_status(self, status="active"):
        params = {} if status.lower() == "all" else {"filter_by": f"Status.{status.title()}"}
        return self.list_all(params=params)

    def list(self, params=None):
        self.list_all_params = params
        return {
            "items": [{"item_id": str(params["page"]), "sku": f"PAGE-{params['page']}"}],
            "page_context": {"has_more_page": params["page"] < 2},
        }

    def mark_inactive_bulk(self, item_ids, batch_size=200):
        results = []
        for start in range(0, len(item_ids), batch_size):
            batch_ids = item_ids[start:start + batch_size]
            response = self.client.request("POST", "items/inactive", params={"item_ids": ",".join(batch_ids)})
            results.append({"item_ids": batch_ids, "response": response})
        return results

    def create(self, payload):
        self.created.append(payload)
        return {"item": {"item_id": f"item-{payload['sku']}"}, "message": "created"}

    def update(self, item_id, payload):
        self.updated.append((item_id, payload))
        return {"item": {"item_id": item_id}}


class FakeClient:
    def __init__(self):
        self.items = FakeItems()
        self.items.client = self
        self.requests = []

    def request(self, method, endpoint, **kwargs):
        self.requests.append((method, endpoint, kwargs))
        return {"code": 0, "message": "success"}


def test_normalize_sku_and_exact_matching():
    target = pd.DataFrame(
        [
            {"SKU": "abc-1", "Item Name": "Existing"},
            {"SKU": "xyz 2", "Item Name": "Missing"},
        ]
    )
    existing = items_to_frame([{"item_id": "1", "sku": "ABC1", "name": "Existing"}])

    diff = find_item_diff(target, existing, compare_fields=[("Item Name", "name", "name")])

    assert normalize_sku(" abc-1 ") == "ABC1"
    assert list(diff["missing"]["SKU"]) == ["xyz 2"]
    assert diff["summary"]["unchanged"] == 1


def test_changed_existing_item_is_reported_not_missing():
    target = pd.DataFrame([{"SKU": "ABC1", "Item Name": "New Name"}])
    existing = items_to_frame([{"item_id": "1", "sku": "ABC1", "name": "Old Name"}])

    diff = find_item_diff(target, existing, compare_fields=[("Item Name", "name", "name")])

    assert diff["missing"].empty
    assert len(diff["changed"]) == 1
    assert "New Name" in diff["changed"].iloc[0]["differences_text"]
    assert "Old Name" in diff["changed"].iloc[0]["differences_text"]


def test_duplicate_target_sku_is_blocking():
    target = pd.DataFrame(
        [
            {"SKU": "ABC1", "Item Name": "One"},
            {"SKU": "abc-1", "Item Name": "Two"},
        ]
    )
    existing = items_to_frame([])

    diff = find_item_diff(target, existing)

    assert len(diff["duplicates"]) == 2
    assert len(diff["blocking"]) == 2
    assert diff["missing"].empty


def test_build_inventory_item_payload_defaults_and_validation():
    defaults = {
        "account_id": "sales",
        "purchase_account_id": "purchase",
        "inventory_account_id": "inventory",
    }
    tax_preferences = [{"tax_id": "gst18"}]
    row = pd.Series(
        {
            "SKU": "FAN1",
            "Item Name": "Fan One",
            "HSN/SAC": "8414",
            "Rate": 100,
            "Purchase Rate": 80,
        }
    )

    payload, issues = build_inventory_item_payload(row, defaults=defaults, tax_preferences=tax_preferences)

    assert issues == []
    assert payload["sku"] == "FAN1"
    assert payload["account_id"] == "sales"
    assert payload["purchase_account_id"] == "purchase"
    assert payload["inventory_account_id"] == "inventory"
    assert payload["item_tax_preferences"] == tax_preferences


def test_build_inventory_item_payload_reports_missing_required_values():
    payload, issues = build_inventory_item_payload(pd.Series({}), defaults={})

    assert payload["sku"] == ""
    assert "missing SKU" in issues
    assert "missing Item Name" in issues
    assert "HSN/SAC missing" in issues


def test_fetch_uses_sdk_list_all_with_purchase_account():
    client = FakeClient()

    items = fetch_items_for_purchase_account(client, "purchase-1")

    assert items[0]["sku"] == "ABC-1"
    assert client.items.list_all_params == {"purchase_account_id": "purchase-1"}


def test_fetch_items_by_status_uses_active_filter():
    client = FakeClient()

    fetch_items_by_status(client, "active")

    assert client.items.list_all_params == {"filter_by": "Status.Active"}


def test_fetch_inventory_items_supports_bounded_pagination():
    client = FakeClient()

    items = fetch_inventory_items(client, "purchase-1", max_pages=1)

    assert [item["sku"] for item in items] == ["PAGE-1"]
    assert client.items.list_all_params == {
        "page": 1,
        "per_page": 200,
        "purchase_account_id": "purchase-1",
    }


def test_find_active_items_with_name_containing_old_is_case_insensitive():
    client = FakeClient()
    items = [
        {"item_id": "1", "name": "Fan_old", "status": "active"},
        {"item_id": "2", "name": "FAN_OLD spare", "status": "active"},
        {"item_id": "3", "name": "Fan_old inactive", "status": "inactive"},
        {"item_id": "4", "name": "Fan new", "status": "active"},
    ]

    matched = find_active_items_with_name_containing(client, items=items)

    assert [item["item_id"] for item in matched] == ["1", "2"]


def test_mark_inventory_items_inactive_batches_item_ids():
    client = FakeClient()

    results = mark_inventory_items_inactive(client, ["1", "2", "3"], batch_size=2)

    assert len(results) == 2
    assert client.requests == [
        ("POST", "items/inactive", {"params": {"item_ids": "1,2"}}),
        ("POST", "items/inactive", {"params": {"item_ids": "3"}}),
    ]


def test_create_missing_inventory_items_uses_create_only(tmp_path):
    client = FakeClient()
    payloads = [{"sku": "NEW1", "name": "New Item"}]

    results, results_path = create_missing_inventory_items(client, payloads, tmp_path)

    assert results[0]["status"] == "created"
    assert client.items.created == payloads
    assert client.items.updated == []
    assert results_path.exists()


def test_prepare_item_create_payloads_blocks_duplicates(tmp_path):
    rows = pd.DataFrame(
        [
            {"SKU": "ABC1", "Item Name": "One", "HSN/SAC": "8414"},
            {"SKU": "abc-1", "Item Name": "Two", "HSN/SAC": "8414"},
        ]
    )

    prepared = prepare_item_create_payloads(rows, tmp_path)

    assert len(prepared["blocking"]) == 1
    assert "duplicate SKU" in prepared["blocking"].iloc[0]["issues"]
    assert prepared["paths"]["preview_json"].exists()


def test_compare_items_with_inventory_uses_snapshot_and_custom_report_names(tmp_path):
    candidates = pd.DataFrame(
        [
            {"SKU": "EXISTING-1", "Item Name": "Existing"},
            {"SKU": "NEW-2", "Item Name": "New"},
        ]
    )
    snapshot = tmp_path / "snapshot.csv"
    pd.DataFrame([{"item_id": "1", "sku": "existing1", "name": "Existing"}]).to_csv(snapshot, index=False)

    results = compare_items_with_inventory(
        candidates,
        tmp_path,
        existing_items_file=snapshot,
        compare_fields=[("Item Name", "name", "name")],
        report_label="Supplier candidate",
        output_filenames={"missing_csv": "supplier_missing.csv"},
    )

    assert results["summary"]["missing"] == 1
    assert list(results["missing"]["SKU"]) == ["NEW-2"]
    assert results["paths"]["missing_csv"] == tmp_path / "supplier_missing.csv"
    assert results["paths"]["missing_xlsx"].exists()


def test_generic_create_from_sheet_accepts_injected_payload_builder(tmp_path):
    source = tmp_path / "items.xlsx"
    pd.DataFrame([{"SKU": "NEW1", "Item Name": "New Item"}]).to_excel(
        source, sheet_name="Items", index=False
    )
    client = FakeClient()

    def payload_builder(row):
        return {"sku": row["SKU"], "name": row["Item Name"]}, []

    results = create_inventory_items_from_sheet(
        source,
        tmp_path,
        client=client,
        sheet_name="Items",
        payload_builder=payload_builder,
        filename_prefix="supplier_create",
        results_filename="supplier_results.csv",
    )

    assert client.items.created == [{"sku": "NEW1", "name": "New Item"}]
    assert results["paths"]["results_csv"] == tmp_path / "supplier_results.csv"

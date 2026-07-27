from zoho_usable_functions.books.bill_json_audit import (
    build_name_sku_mapping,
    compare_invoice_json_to_bill,
    find_bill_by_number,
    merge_name_sku_mappings,
    normalize_invoice_json,
)


class FakeBills:
    def list(self, params):
        return {"bills": [{"bill_id": "bill-1", "bill_number": params["bill_number"]}]}

    def get(self, bill_id):
        return {"bill": {"bill_id": bill_id, "bill_number": "INV-1"}}


class FakeClient:
    bills = FakeBills()


def test_find_bill_by_number_fetches_detail():
    bill = find_bill_by_number(FakeClient(), "INV-1")

    assert bill["bill_id"] == "bill-1"


def test_compare_invoice_json_to_bill_matches_lines_by_name():
    invoice_json = {
        "inv": {"no": "INV-1", "date": "22.05.2026", "taxable": 100},
        "items": [
            {
                "sku": None,
                "name": "NEOSEAL 105 - 100ML",
                "hsn": "35061000",
                "qty": 2,
                "billed_net_rate": 50,
                "gst": 18,
                "total": 118,
            }
        ],
        "totals": {"tax": 18, "round_off": 0, "net": 118},
    }
    bill = {
        "bill_id": "bill-1",
        "bill_number": "INV-1",
        "date": "2026-05-22",
        "sub_total": 100,
        "tax_total": 18,
        "adjustment": 0,
        "total": 118,
        "line_items": [
            {
                "line_item_id": "line-1",
                "name": "Neoseal 105 100 ml",
                "sku": "NS105-100",
                "hsn_or_sac": "35061000",
                "quantity": 2,
                "rate": 50,
                "item_total": 100,
                "line_item_taxes": [{"tax_amount": 18}],
            }
        ],
    }

    report = compare_invoice_json_to_bill(invoice_json, bill)

    assert report["summary"]["overall_match"] is True
    assert report["line_comparisons"][0]["zoho_sku"] == "NS105-100"


def test_normalize_new_gemini_schema():
    normalized = normalize_invoice_json(
        {
            "invoice_details": {"invoice_number": "INV-2", "invoice_date": "22-May-26"},
            "line_items": [
                {
                    "item_description": "Item",
                    "hsn_sac": "1234",
                    "shipped_qty": 2,
                    "rate": 50,
                    "amount": 100,
                }
            ],
            "totals": {
                "subtotal": 100,
                "discount": -5,
                "igst_amount": 17.1,
                "round_off": -0.1,
                "total_amount": 112,
            },
        }
    )

    assert normalized["inv"]["taxable"] == 95
    assert normalized["items"][0]["name"] == "Item"
    assert normalized["totals"]["discount"] == -5


def test_build_name_sku_mapping_keeps_only_requested_fields():
    mapping = build_name_sku_mapping(
        {
            "line_comparisons": [
                {
                    "matched": True,
                    "json_name": "Gemini item",
                    "zoho_name": "Zoho item",
                    "zoho_sku": "SKU-1",
                    "differences": ["hsn"],
                },
                {"matched": False, "json_name": "Unmatched"},
            ],
            "bill_number": "INV-1",
        }
    )

    assert mapping == [
        {
            "invoice_number": "INV-1",
            "json_name": "Gemini item",
            "zoho_name": "Zoho item",
            "zoho_sku": "SKU-1",
        }
    ]


def test_merge_name_sku_mappings_updates_same_invoice_and_preserves_others():
    existing = [
        {"invoice_number": "INV-1", "json_name": "Item A", "zoho_sku": "OLD"},
        {"invoice_number": "INV-2", "json_name": "Item B", "zoho_sku": "KEEP"},
    ]
    updates = [{"invoice_number": "INV-1", "json_name": "Item A", "zoho_sku": "NEW"}]

    merged = merge_name_sku_mappings(existing, updates)

    assert merged == [
        {"invoice_number": "INV-2", "json_name": "Item B", "zoho_sku": "KEEP"},
        {"invoice_number": "INV-1", "json_name": "Item A", "zoho_sku": "NEW"},
    ]


def test_structured_matching_prevents_similar_sizes_from_cross_matching():
    invoice_json = {
        "invoice_details": {"invoice_number": "INV-3", "invoice_date": "26-May-26"},
        "line_items": [
            {
                "item_description": "PVC BALL VALVE 3/4",
                "hsn_sac": "84818090",
                "shipped_qty": 240,
                "rate": 52.62,
                "amount": 12628.8,
            },
            {
                "item_description": "PVC BALL VALVE 1 INCH",
                "hsn_sac": "84818090",
                "shipped_qty": 120,
                "rate": 74.69,
                "amount": 8962.8,
            },
        ],
        "totals": {
            "subtotal": 21591.6,
            "discount": 0,
            "igst_amount": 0,
            "round_off": 0,
            "total_amount": 21591.6,
        },
    }
    bill = {
        "bill_number": "INV-3",
        "date": "2026-05-26",
        "sub_total": 21591.6,
        "discount": 0,
        "tax_total": 0,
        "adjustment": 0,
        "total": 21591.6,
        "line_items": [
            {
                "line_item_id": "one",
                "name": "1 PVC Ball Valve",
                "sku": "1-PVC",
                "hsn_or_sac": "84818090",
                "quantity": 120,
                "rate": 74.69,
                "item_total": 8962.8,
            },
            {
                "line_item_id": "three-quarter",
                "name": "0.75 PVC Ball Valve",
                "sku": "0.75-PVC",
                "hsn_or_sac": "84818090",
                "quantity": 240,
                "rate": 52.62,
                "item_total": 12628.8,
            },
        ],
    }

    report = compare_invoice_json_to_bill(invoice_json, bill)

    assert [line["zoho_sku"] for line in report["line_comparisons"]] == ["0.75-PVC", "1-PVC"]

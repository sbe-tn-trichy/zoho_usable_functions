import importlib.util
from pathlib import Path

import pandas as pd


SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "inventory"
    / "neoseal"
    / "Neoseal_items_normalizer.py"
)
SPEC = importlib.util.spec_from_file_location("neoseal_items_normalizer", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _item(**overrides):
    item = {
        "Group Name": "UPVC Ball Valve",
        "Item Name": '1" UPVC Ball Valve GS',
        "SKU": "1-UPVC-GS",
        "Cost Price": 80,
        "Sales Price": 100,
        "Margin": 20,
        "ItemId": "00123",
    }
    item.update(overrides)
    return item


def test_audit_returns_only_anomalous_items_by_area():
    source = pd.DataFrame(
        [
            _item(),
            _item(
                **{
                    "Group Name": "PVC Ball Valve",
                    "Item Name": '0.75" UPVC Ball Valve MS Handle',
                    "SKU": "upvc ms",
                    "ItemId": "456",
                }
            ),
        ]
    )

    report = MODULE.audit_neoseal_items(source)

    assert len(report) == 1
    anomaly = report.iloc[0]
    assert anomaly["Expected Group"] == "UPVC Ball Valve"
    assert anomaly["Anomaly Areas"] == "grouping; sku"
    assert "Grouping:\n" in anomaly["Anomaly Details"]
    assert "expected 'UPVC Ball Valve'" in anomaly["Anomaly Details"]
    assert "\n\nSKU:\n" in anomaly["Anomaly Details"]
    assert "whitespace" in anomaly["Anomaly Details"]
    assert "lowercase" in anomaly["Anomaly Details"]


def test_audit_flags_naming_conventions_and_product_code_terminology():
    source = pd.DataFrame(
        [
            _item(
                **{
                    "Group Name": "",
                    "Item Name": "507 DEMP KILL-10 LTR",
                    "SKU": "damp kill",
                }
            )
        ]
    )

    anomaly = MODULE.audit_neoseal_items(source).iloc[0]

    assert anomaly["Expected Group"] == "Damp Kill"
    assert "Naming:\n" in anomaly["Anomaly Details"]
    assert "\n\nGrouping:\n" in anomaly["Anomaly Details"]
    assert "\n\nSKU:\n" in anomaly["Anomaly Details"]
    assert "all uppercase" in anomaly["Anomaly Details"]
    assert "Damp Kill" in anomaly["Anomaly Details"]
    assert "use 'L'" in anomaly["Anomaly Details"]
    assert "product code 507" in anomaly["Anomaly Details"]


def test_audit_flags_duplicate_skus():
    source = pd.DataFrame(
        [
            _item(),
            _item(
                **{
                    "Item Name": '0.75" UPVC Ball Valve GS',
                    "SKU": "1-upvc-gs",
                    "ItemId": "456",
                }
            ),
        ]
    )

    report = MODULE.audit_neoseal_items(source)

    assert len(report) == 2
    assert report["Anomaly Details"].str.contains("duplicate SKU").all()

---
type: Concept
title: Package Boundary
description: Ownership and compatibility boundaries between zoho_usable_functions and zoho-sdk workflows.
tags: [architecture, dependencies, workflows, compatibility]
status: active
---

# Package Boundary

The `zoho-sdk[workflows]` dependency owns confirmed bank reconciliation,
vendor-ledger reconciliation, Zeiss PDF parsing, Polycab credit-memo processing,
and their shared workflow models and exceptions.

This package owns incubating or company-specific inventory, GST, payment,
customer-audit, and stock utilities. Legacy reconciliation and credit-memo
module paths are compatibility aliases to SDK modules, not implementation
forks. New code should import confirmed workflows from `workflows` directly.
Inventory item-group creation delegates to the typed SDK
`client.items.group_items` resource method; only unsupported update operations
may use the lower-level request layer.

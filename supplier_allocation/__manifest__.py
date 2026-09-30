# -*- coding: utf-8 -*-
{
    "name": "Supplier Allocation",
    "summary": "Allocate replenishment quantities across multiple vendors before RFQs",
    "description": """
Supplier Allocation adds a review step to replenishment so purchasing users can
split a required quantity across available product vendors before creating RFQs.
    """,
    "author": "My Company",
    "website": "https://www.yourcompany.com",
    "category": "Inventory/Purchase",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "purchase",
        "purchase_stock",
    ],
    "data": [
        "views/supplier_allocation_wizard_view.xml",
        "views/stock_warehouse_orderpoint_views.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
}

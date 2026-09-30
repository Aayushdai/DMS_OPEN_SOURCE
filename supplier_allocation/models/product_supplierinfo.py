# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductSupplierinfo(models.Model):
    _inherit = "product.supplierinfo"

    max_allocation_qty = fields.Float(
        string="Maximum Allocation Quantity",
        digits="Product Unit",
        help=(
            "Optional maximum quantity this vendor should receive in one "
            "supplier allocation. Leave empty for no allocation limit."
        ),
    )

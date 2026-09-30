# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


class StockWarehouseOrderpoint(models.Model):
    _inherit = "stock.warehouse.orderpoint"

    def action_open_supplier_allocation(self):
        self.ensure_one()
        if self.product_uom.compare(self.qty_to_order, 0.0) <= 0:
            raise UserError(_("There is no quantity to allocate for this replenishment."))

        wizard = self.env["supplier.allocation.wizard"].create(
            {
                "orderpoint_id": self.id,
                "required_qty": self.qty_to_order,
            }
        )
        wizard.action_recalculate()
        return {
            "name": _("Supplier Allocation"),
            "type": "ir.actions.act_window",
            "res_model": "supplier.allocation.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

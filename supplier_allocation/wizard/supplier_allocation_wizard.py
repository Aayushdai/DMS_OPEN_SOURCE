# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError


class SupplierAllocationWizard(models.TransientModel):
    _name = "supplier.allocation.wizard"
    _description = "Supplier Allocation Wizard"

    orderpoint_id = fields.Many2one(
        "stock.warehouse.orderpoint",
        string="Replenishment",
        required=True,
        readonly=True,
    )

    product_id = fields.Many2one(
        related="orderpoint_id.product_id",
        string="Product",
        readonly=True,
    )

    product_uom_id = fields.Many2one(
        related="orderpoint_id.product_uom",
        string="Unit of Measure",
        readonly=True,
    )

    required_qty = fields.Float(
        string="Required Quantity",
        digits="Product Unit",
        required=True,
        readonly=True,
    )

    line_ids = fields.One2many(
        "supplier.allocation.wizard.line",
        "wizard_id",
        string="Supplier Comparison",
    )

    total_allocated_qty = fields.Float(
        string="Total Allocated",
        compute="_compute_total_allocated_qty",
        digits="Product Unit",
    )

    error_message = fields.Text(
        string="Allocation Message",
        readonly=True,
    )

    rfq_created = fields.Boolean(
        string="RFQ Created",
        readonly=True,
    )

    purchase_order_ids = fields.Many2many(
        "purchase.order",
        string="Created RFQs",
        readonly=True,
    )

    @api.depends("line_ids.allocated_qty")
    def _compute_total_allocated_qty(self):
        for wizard in self:
            wizard.total_allocated_qty = sum(
                wizard.line_ids.mapped("allocated_qty")
            )

    def action_recalculate(self):
        self.ensure_one()
        self._recalculate_lines()
        return False

    def action_create_rfqs(self):
        self.ensure_one()

        if self.rfq_created:
            raise UserError(
                _("An RFQ has already been created for this allocation.")
            )

        lines = self.line_ids.filtered(
            lambda line: line.allocated_qty > 0.0
        )

        self._validate_allocation(lines)

        buy_rule = self.orderpoint_id.rule_ids.filtered(
            lambda rule: rule.action == "buy"
        )[:1]

        if not buy_rule:
            buy_rule = self.orderpoint_id._get_default_rule()

        if not buy_rule or buy_rule.action != "buy":
            raise UserError(
                _("This replenishment does not use a purchase route.")
            )

        created_orders = self.env["purchase.order"]

        for line in lines:
            created_orders |= self._create_rfq_for_line(
                buy_rule,
                line,
            )

        self.write(
            {
                "rfq_created": True,
                "purchase_order_ids": [(6, 0, created_orders.ids)],
            }
        )

        self.orderpoint_id.action_remove_manual_qty_to_order()
        self.orderpoint_id._compute_qty_to_order()

        return {
            "name": _("Created RFQ"),
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [("id", "in", created_orders.ids)],
        }

    def _recalculate_lines(self):
        self.ensure_one()

        sellers = self._get_available_sellers()

        allocations, message = self._allocate_by_price_ratio(
            sellers
        )

        self.line_ids.unlink()

        commands = []

        for seller in sellers:
            price = self._get_seller_price(seller)
            min_qty = self._seller_min_qty(seller)

            commands.append(
                (
                    0,
                    0,
                    {
                        "supplierinfo_id": seller.id,
                        "partner_id": seller.partner_id.id,
                        "price": price,
                        "min_qty": min_qty,
                        "max_allocation_qty": seller.max_allocation_qty,
                        "allocated_qty": allocations.get(
                            seller.id,
                            0.0,
                        ),
                    },
                )
            )

        self.write(
            {
                "line_ids": commands,
                "error_message": message,
            }
        )

    def _get_available_sellers(self):
        self.ensure_one()

        sellers = self.product_id._prepare_sellers(False)

        return sellers._get_filtered_supplier(
            self.orderpoint_id.company_id,
            self.product_id,
        )

    def _get_seller_price(self, seller):
        price = seller.price_discounted or seller.price

        return price

    def _allocate_by_price_ratio(self, sellers):
    
        self.ensure_one()

        if not sellers:
            return {}, _(
            "No suppliers are available for this product."
        )

        supplier_options = []

        for seller in sellers:
            price = self._get_seller_price(seller)
            min_qty = self._seller_min_qty(seller)

            supplier_options.append(
            {
                "seller": seller,
                "price": price,
                "min_qty": min_qty,
            }
        )

        if not supplier_options:
            return {}, _(
                "No supplier is available for price comparison."
        )

        selected = min(
            supplier_options,
            key=lambda option: (
                option["price"],
                option["seller"].sequence,
            ),
        )

        selected_seller = selected["seller"]

        allocations = {
        seller.id: 0.0
        for seller in sellers
    }

        allocations[selected_seller.id] = self.required_qty

        return allocations, False

    def _seller_min_qty(self, seller):
        self.ensure_one()

        return seller.product_uom_id._compute_quantity(
            seller.min_qty,
            self.product_uom_id,
            rounding_method="HALF-UP",
        )

    def _validate_allocation(self, lines):
        self.ensure_one()

        if not lines:
            raise UserError(
            _("No supplier has been selected.")
        )

        if len(lines) != 1:
            raise UserError(
            _(
                "Only one supplier can be selected "
                "for a replenishment."
            )
        )

        total_allocated = sum(
            lines.mapped("allocated_qty")
        )

        if self.product_uom_id.compare(
            total_allocated,
            self.required_qty,
        ) != 0:
            raise UserError(
            _(
                "The allocated quantity must equal "
                "the required quantity."
            )
        )

    def _create_rfq_for_line(self, rule, line):
        self.ensure_one()

        orderpoint = self.orderpoint_id

        date = orderpoint._get_orderpoint_procurement_date()

        horizon_days = orderpoint.get_horizon_days()

        if horizon_days:
            date -= relativedelta(
                days=int(horizon_days)
            )

        values = orderpoint._prepare_procurement_values(
            date=date
        )

        values.update(
            {
                "orderpoint_id": orderpoint,
                "supplierinfo_id": line.supplierinfo_id,
                "supplier": line.supplierinfo_id,
                "propagate_cancel": rule.propagate_cancel,
            }
        )

        origin = orderpoint.name

        procurement = self.env["stock.rule"].Procurement(
            orderpoint.product_id,
            line.allocated_qty,
            orderpoint.product_uom,
            orderpoint.location_id,
            orderpoint.name,
            origin,
            orderpoint.company_id,
            values,
        )

        po_values = rule._prepare_purchase_order(
            orderpoint.company_id,
            {origin},
            [values],
        )

        purchase_order = (
            self.env["purchase.order"]
            .with_user(SUPERUSER_ID)
            .create(po_values)
        )

        po_line_values = self.env[
            "purchase.order.line"
        ]._prepare_purchase_order_line_from_procurement(
            *procurement,
            purchase_order,
        )

        self.env[
            "purchase.order.line"
        ].with_user(SUPERUSER_ID).create(
            po_line_values
        )

        return purchase_order


class SupplierAllocationWizardLine(models.TransientModel):
    _name = "supplier.allocation.wizard.line"
    _description = "Supplier Allocation Wizard Line"
    _order = "id"

    wizard_id = fields.Many2one(
        "supplier.allocation.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )

    supplierinfo_id = fields.Many2one(
        "product.supplierinfo",
        string="Vendor Pricelist",
        required=True,
        readonly=True,
    )

    partner_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        required=True,
        readonly=True,
    )

    price = fields.Float(
        string="Vendor Price",
        readonly=True,
    )

    min_qty = fields.Float(
        string="Minimum Qty",
        digits="Product Unit",
        readonly=True,
    )

    price_ratio = fields.Float(
        string="Price Ratio",
        digits="Product Unit",
        compute="_compute_price_ratio",
        readonly=True,
    )

    max_allocation_qty = fields.Float(
        string="Maximum Allocation",
        digits="Product Unit",
    )

    allocated_qty = fields.Float(
        string="Allocated Quantity",
        digits="Product Unit",
    )

    @api.depends("price", "min_qty")
    def _compute_price_ratio(self):
        for line in self:
            if line.min_qty > 0:
                line.price_ratio = line.price / line.min_qty
            else:
                line.price_ratio = 0.0
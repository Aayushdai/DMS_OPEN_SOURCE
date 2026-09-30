from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    documents_binary_max_size = fields.Integer(
        string="File Size",
        default=25,
        config_parameter="dms.binary_max_size",
    )

    documents_forbidden_extensions = fields.Char(
        string="File Extensions",
        config_parameter="dms.forbidden_extensions",
    )
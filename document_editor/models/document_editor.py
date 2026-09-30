from odoo import models
from odoo.exceptions import AccessError


class DmsFile(models.Model):
    _inherit = "dms.file"

    def action_open_onlyoffice(self):
        self.ensure_one()

        if (self.extension or "").lower() != "docx":
            raise AccessError("ONLYOFFICE editing is available for DOCX files only.")

        if not self.permission_write:
            raise AccessError("You do not have permission to edit this document.")

        return {
            "type": "ir.actions.act_url",
            "url": f"/document_editor/dms/open/{self.id}",
            "target": "self",
        }
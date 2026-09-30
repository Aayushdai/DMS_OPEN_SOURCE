from odoo import models
from odoo.exceptions import AccessError


class DmsFile(models.Model):
    _inherit = "dms.file"

    def action_open_onlyoffice(self):
        self.ensure_one()

        supported_extensions = {
            # Document editor
            "docx",
            "md",

            # Spreadsheet editor
            "xlsx",
            "csv",

            # Presentation editor
            "pptx",

            # PDF editor
            "pdf",
        }

        extension = (self.extension or "").lower()

        if extension not in supported_extensions:
            raise AccessError(
                "ONLYOFFICE editing is available for "
                "DOCX, XLSX, PPTX, CSV, PDF and Markdown files."
            )

        if not self.permission_write:
            raise AccessError(
                "You do not have permission to edit this document."
            )

        return {
            "type": "ir.actions.act_url",
            "url": f"/document_editor/dms/open/{self.id}",
            "target": "self",
        }
import base64
import hashlib
import hmac
import json
import logging
from urllib.parse import quote, urlsplit, urlunsplit

import jwt
import requests

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class DocumentEditorController(http.Controller):

    def _get_parameter(self, key, default=False):
        parameter = (
            request.env["ir.config_parameter"]
            .sudo()
            .search([("key", "=", key)], limit=1)
        )
        return parameter.value if parameter else default

    def _get_editor_secret(self):
        return self._get_parameter(
            "document_editor.onlyoffice_jwt_secret"
        )

    def _get_onlyoffice_internal_url(self):
        return self._get_parameter(
            "document_editor.onlyoffice_internal_url",
            "http://onlyoffice",
        ).rstrip("/")

    def _get_onlyoffice_download_url(self, edited_url):
        """Convert ONLYOFFICE browser URL to Docker-internal URL."""
        if not edited_url:
            return edited_url

        internal_url = urlsplit(
            self._get_onlyoffice_internal_url()
        )
        document_url = urlsplit(edited_url)

        return urlunsplit(
            (
                internal_url.scheme or document_url.scheme,
                internal_url.netloc or document_url.netloc,
                document_url.path,
                document_url.query,
                document_url.fragment,
            )
        )

    def _make_token(self, file_record):
        secret = self._get_editor_secret()

        if not secret:
            return False

        message = f"{file_record.id}:{file_record.checksum}".encode()

        return hmac.new(
            secret.encode(),
            message,
            hashlib.sha256,
        ).hexdigest()

    def _check_token(self, file_record, token):
        expected = self._make_token(file_record)

        return (
            bool(expected and token)
            and hmac.compare_digest(token, expected)
        )

    # ---------------------------------------------------------
    # OPEN EDITOR
    # ---------------------------------------------------------

    @http.route(
        "/document_editor/dms/open/<int:file_id>",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def open_editor(self, file_id, **kwargs):
        dms_file = request.env["dms.file"].browse(file_id)

        if not dms_file.exists():
            return request.not_found()

        filename = dms_file.name or ""

        if not filename.lower().endswith(".docx"):
            return request.make_response(
                "ONLYOFFICE editing is currently available "
                "for DOCX files only.",
                headers=[
                    (
                        "Content-Type",
                        "text/plain; charset=utf-8",
                    )
                ],
                status=400,
            )

        onlyoffice_url = self._get_parameter(
            "document_editor.onlyoffice_url",
            "http://localhost:8080",
        )

        config_url = (
            f"/document_editor/dms/config/{dms_file.id}"
        )

        dms_action = request.env.ref(
            "dms.action_dms_file"
        )

        return_url = (
            f"/odoo/action-{dms_action.id}/{dms_file.id}"
        )

        return request.render(
            "document_editor.onlyoffice_editor_page",
            {
                "file": dms_file,
                "config_url": config_url,
                "onlyoffice_url": onlyoffice_url.rstrip("/"),
                "return_url": return_url,
            },
        )

    # ---------------------------------------------------------
    # ONLYOFFICE CONFIG
    # ---------------------------------------------------------

    @http.route(
        "/document_editor/dms/config/<int:file_id>",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def editor_config(self, file_id, **kwargs):
        dms_file = request.env["dms.file"].browse(file_id)

        if not dms_file.exists():
            return request.not_found()

        filename = dms_file.name or ""

        if not filename.lower().endswith(".docx"):
            return request.make_response(
                json.dumps(
                    {
                        "error": "Only DOCX files are supported."
                    }
                ),
                headers=[
                    ("Content-Type", "application/json")
                ],
                status=400,
            )

        if not dms_file.permission_write:
            return request.make_response(
                json.dumps(
                    {
                        "error": (
                            "You do not have permission "
                            "to edit this document."
                        )
                    }
                ),
                headers=[
                    ("Content-Type", "application/json")
                ],
                status=403,
            )

        secret = self._get_editor_secret()

        if not secret:
            _logger.error(
                "ONLYOFFICE JWT secret is not configured."
            )

            return request.make_response(
                json.dumps(
                    {
                        "error": (
                            "ONLYOFFICE JWT secret "
                            "is not configured."
                        )
                    }
                ),
                headers=[
                    ("Content-Type", "application/json")
                ],
                status=500,
            )

        odoo_base_url = self._get_parameter(
            "document_editor.odoo_base_url",
            "http://odoo20-web:8069",
        ).rstrip("/")

        token = self._make_token(dms_file)

        if not token:
            return request.make_response(
                json.dumps(
                    {
                        "error": (
                            "Unable to generate "
                            "document access token."
                        )
                    }
                ),
                headers=[
                    ("Content-Type", "application/json")
                ],
                status=500,
            )

        content_url = (
            f"{odoo_base_url}"
            f"/document_editor/dms/content/{dms_file.id}"
            f"?token={quote(token)}"
        )

        callback_url = (
            f"{odoo_base_url}"
            f"/document_editor/dms/callback/{dms_file.id}"
            f"?token={quote(token)}"
        )

        # IMPORTANT:
        # This must remain a normal Python dictionary.
        config = {
            "documentType": "word",

            "document": {
                "fileType": "docx",
                "key": (
                    f"dms-{dms_file.id}-"
                    f"{dms_file.checksum}"
                ),
                "title": filename,
                "url": content_url,

                "permissions": {
                    "edit": True,
                    "download": True,
                    "print": True,
                },
            },

            "editorConfig": {
                "mode": "edit",
                "callbackUrl": callback_url,

                "customization": {
                    "forcesave": True,
                    "savetitle": True,
                },
            

                "user": {
                    "id": str(request.env.user.id),
                    "name": request.env.user.name or "User",
                },
            },
        }

        # Generate the JWT from the dictionary.
        config["token"] = jwt.encode(
            config,
            secret,
            algorithm="HS256",
        )

        _logger.info(
            "ONLYOFFICE config generated for DMS file %s",
            dms_file.id,
        )

        return request.make_response(
            json.dumps(config),
            headers=[
                ("Content-Type", "application/json")
            ],
        )

    # ---------------------------------------------------------
    # DOCUMENT CONTENT
    # ---------------------------------------------------------

    @http.route(
        "/document_editor/dms/content/<int:file_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def document_content(
        self,
        file_id,
        token=None,
        **kwargs,
    ):
        dms_file = (
            request.env["dms.file"]
            .sudo()
            .browse(file_id)
        )

        if not dms_file.exists():
            return request.not_found()

        if not self._check_token(dms_file, token):
            return request.make_response(
                "Invalid token",
                status=403,
            )

        filename = dms_file.name or ""

        if not filename.lower().endswith(".docx"):
            return request.make_response(
                "Only DOCX files are supported.",
                status=400,
            )

        content = dms_file.content

        if not content:
            return request.make_response(
                "File has no content.",
                status=404,
            )

        if isinstance(content, str):
            binary = base64.b64decode(content)
        else:
            binary = bytes(content)

        return request.make_response(
            binary,
            headers=[
                (
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document",
                ),
                (
                    "Content-Disposition",
                    f"inline; filename*=UTF-8''{quote(filename)}",
                ),
            ],
        )

    # ---------------------------------------------------------
    # ONLYOFFICE CALLBACK
    # ---------------------------------------------------------

    @http.route(
        "/document_editor/dms/callback/<int:file_id>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def dms_callback(
        self,
        file_id,
        token=None,
        **kwargs,
    ):
        dms_file = (
            request.env["dms.file"]
            .sudo()
            .browse(file_id)
        )

        if not dms_file.exists():
            return request.make_response(
                json.dumps({"error": 1}),
                headers=[
                    ("Content-Type", "application/json")
                ],
                status=404,
            )

        if not self._check_token(dms_file, token):
            return request.make_response(
                json.dumps({"error": 1}),
                headers=[
                    ("Content-Type", "application/json")
                ],
                status=403,
            )

        try:
            data = (
                request.httprequest.get_json(
                    silent=True
                )
                or {}
            )

            status = data.get("status")

            _logger.info(
                "ONLYOFFICE callback for DMS file %s: "
                "status=%s, forcesavetype=%s",
                file_id,
                status,
                data.get("forcesavetype"),
            )

            # Status 2:
            # Document ready after editor closes.
            #
            # Status 6:
            # Current document state was force-saved.
            if status in (2, 6):
                edited_url = data.get("url")

                if not edited_url:
                    raise ValueError(
                        "ONLYOFFICE did not provide "
                        "an edited document URL."
                    )

                download_url = (
                    self._get_onlyoffice_download_url(
                        edited_url
                    )
                )

                _logger.info(
                    "Downloading edited DOCX for DMS file %s "
                    "from ONLYOFFICE: %s",
                    file_id,
                    download_url,
                )

                response = requests.get(
                    download_url,
                    timeout=60,
                )

                response.raise_for_status()

                binary = response.content

                if not binary.startswith(b"PK"):
                    raise ValueError(
                        "ONLYOFFICE returned data that is "
                        "not a DOCX/OOXML ZIP file."
                    )

                dms_file.write(
                    {
                        "content": (
                            base64.b64encode(binary)
                            .decode("ascii")
                        ),
                    }
                )

                _logger.info(
                    "Successfully saved updated DOCX "
                    "to DMS file %s (%s bytes)",
                    file_id,
                    len(binary),
                )

            elif status in (3, 7):
                _logger.error(
                    "ONLYOFFICE reported a save error "
                    "for DMS file %s: %s",
                    file_id,
                    data,
                )

            return request.make_response(
                json.dumps({"error": 0}),
                headers=[
                    ("Content-Type", "application/json")
                ],
            )

        except Exception:
            _logger.exception(
                "ONLYOFFICE callback failed "
                "for DMS file %s",
                file_id,
            )

            return request.make_response(
                json.dumps({"error": 1}),
                headers=[
                    ("Content-Type", "application/json")
                ],
                status=500,
            )
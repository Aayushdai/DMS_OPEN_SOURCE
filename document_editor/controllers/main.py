import base64

import hashlib

import hmac

import json

import logging

from datetime import datetime, timedelta, timezone

from urllib.parse import quote, urlsplit, urlunsplit



import jwt

import requests



from odoo import _, http

from odoo.http import request





_logger = logging.getLogger(__name__)





class DocumentEditorController(http.Controller):



    # ---------------------------------------------------------

    # CONFIGURATION

    # ---------------------------------------------------------



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

            "http\://onlyoffice",

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



    # ---------------------------------------------------------

    # SUPPORTED FILE TYPES

    # ---------------------------------------------------------



    OFFICE_FILE_TYPES = {

        # -----------------------------------------------------

        # WORD / DOCUMENT EDITOR

        # -----------------------------------------------------



        "docx": {

            "document_type": "word",

            "mimetype": (

                "application/vnd.openxmlformats-officedocument."

                "wordprocessingml.document"

            ),

            "label": "DOCX",

            "binary_type": "ooxml",

        },



        "md": {

            "document_type": "word",

            "mimetype": "text/markdown; charset=utf-8",

            "label": "Markdown",

            "binary_type": "text",

        },



        # -----------------------------------------------------

        # SPREADSHEET EDITOR

        # -----------------------------------------------------



        "xlsx": {

            "document_type": "cell",

            "mimetype": (

                "application/vnd.openxmlformats-officedocument."

                "spreadsheetml.sheet"

            ),

            "label": "XLSX",

            "binary_type": "ooxml",

        },



        "csv": {

            "document_type": "cell",

            "mimetype": "text/csv; charset=utf-8",

            "label": "CSV",

            "binary_type": "text",

        },



        # -----------------------------------------------------

        # PDF EDITOR

        # -----------------------------------------------------



        "pdf": {

            "document_type": "pdf",

            "mimetype": "application/pdf",

            "label": "PDF",

            "binary_type": "pdf",

        },



        # -----------------------------------------------------

        # PRESENTATION EDITOR

        # -----------------------------------------------------



        "pptx": {

            "document_type": "slide",

            "mimetype": (

                "application/vnd.openxmlformats-officedocument."

                "presentationml.presentation"

            ),

            "label": "PPTX",

            "binary_type": "ooxml",

        },

    }



    def _get_office_file_info(self, filename):

        """Return ONLYOFFICE information for a supported file."""

        extension = ""



        if filename and "." in filename:

            extension = filename.rsplit(".", 1)[-1].lower()



        return self.OFFICE_FILE_TYPES.get(extension)



    def _get_file_extension(self, filename):

        if not filename or "." not in filename:

            return ""



        return filename.rsplit(".", 1)[-1].lower()



    # ---------------------------------------------------------

    # FILE CONTENT

    # ---------------------------------------------------------



    def _get_file_binary(self, dms_file):

        """Return DMS file content as raw bytes."""

        content = dms_file.content



        if not content:

            return b""



        if isinstance(content, str):

            return base64.b64decode(content)



        return bytes(content)



    def _validate_binary(self, binary, file_info, extension):

        """

        Validate that the downloaded file looks like the expected

        document type.



        DOCX/XLSX/PPTX are OOXML ZIP packages.

        PDF starts with %PDF.

        CSV/MD are text based.

        """



        if not binary:

            raise ValueError(

                "ONLYOFFICE returned an empty file."

            )



        binary_type = file_info["binary_type"]



        # OOXML files are ZIP containers.

        if binary_type == "ooxml":

            if not binary.startswith(b"PK"):

                raise ValueError(

                    f"ONLYOFFICE returned invalid "

                    f"{extension.upper()} data."

                )

            return



        # PDF files start with %PDF.

        if binary_type == "pdf":

            if not binary.startswith(b"%PDF"):

                raise ValueError(

                    "ONLYOFFICE returned invalid PDF data."

                )

            return



        # CSV / Markdown are text files.

        if binary_type == "text":

            try:

                binary.decode("utf-8")

            except UnicodeDecodeError:

                raise ValueError(

                    f"ONLYOFFICE returned invalid UTF-8 "

                    f"{extension.upper()} data."

                )



    # ---------------------------------------------------------

    # CONTENT TOKEN

    # ---------------------------------------------------------



    def _make_token(self, file_record):

        """

        Token used by ONLYOFFICE to download the current source file.

        """



        secret = self._get_editor_secret()



        if not secret:

            return False



        message = (

            f"{file_record.id}:{file_record.checksum}"

        ).encode()



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

    # CALLBACK TOKEN

    # ---------------------------------------------------------



    def _make_callback_token(self, file_record):

        """

        Signed token used to authenticate ONLYOFFICE callbacks.

        """



        secret = self._get_editor_secret()



        if not secret:

            return False



        payload = {

            "purpose": "dms_callback",

            "file_id": file_record.id,

            "user_id": request.env.user.id,

            "exp": (

                datetime.now(timezone.utc)

                + timedelta(hours=24)

            ),

        }



        return jwt.encode(

            payload,

            secret,

            algorithm="HS256",

        )



    def _decode_callback_token(self, file_record, token):

        """Validate and decode the callback token."""



        secret = self._get_editor_secret()



        if not secret or not token:

            return False



        try:

            payload = jwt.decode(

                token,

                secret,

                algorithms=["HS256"],

            )

        except jwt.InvalidTokenError:

            return False



        if payload.get("purpose") != "dms_callback":

            return False



        try:

            token_file_id = int(

                payload.get("file_id", 0)

            )

        except (TypeError, ValueError):

            return False



        if token_file_id != file_record.id:

            return False



        return payload



    # ---------------------------------------------------------

    # EDITOR USER

    # ---------------------------------------------------------



    def _get_editor_user(

        self,

        data,

        callback_payload,

    ):

        """

        Determine which Odoo user last edited the document.



        ONLYOFFICE sends the last editor's identifier in \`users\`

        for changed status 2 and 6 callbacks.



        The user stored inside the signed callback token is

        used as a fallback.

        """



        editor_user = (

            request.env["res.users"]

            .sudo()

            .browse()

        )



        user_ids = data.get("users") or []



        if user_ids:

            try:

                editor_uid = int(user_ids[-1])

            except (TypeError, ValueError):

                editor_uid = False



            if editor_uid:

                editor_user = (

                    request.env["res.users"]

                    .sudo()

                    .browse(editor_uid)

                )



            if not editor_user.exists():

                editor_user = (

                    request.env["res.users"]

                    .sudo()

                    .browse()

                )



        # Fallback to the user that opened the editor.

        if not editor_user.exists():

            try:

                token_user_id = int(

                    callback_payload.get(

                        "user_id",

                        0,

                    )

                )

            except (TypeError, ValueError):

                token_user_id = False



            if token_user_id:

                editor_user = (

                    request.env["res.users"]

                    .sudo()

                    .browse(token_user_id)

                )



        if not editor_user.exists():

            return request.env.user



        return editor_user



    # ---------------------------------------------------------

    # AUDIT

    # ---------------------------------------------------------



    def _post_edit_audit(

        self,

        dms_file,

        editor_user,

    ):

        """Post the edit event to the existing DMS Chatter."""



        dms_file.message_post(

            body=_(

                "Document content was modified "

                "using ONLYOFFICE."

            ),

            author_id=editor_user.partner_id.id,

            message_type="comment",

            subtype_xmlid="mail.mt_note",

        )



    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # UNSAVED EDIT AUDIT
    # ---------------------------------------------------------



    @http.route(
        "/document_editor/dms/unsaved-audit/<int:file_id>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def unsaved_edit_audit(
        self,
        file_id,
        token=None,
        initial_checksum=None,
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
        if (
            not initial_checksum
            or dms_file.checksum != initial_checksum
        ):
            return request.make_response(
                json.dumps({
                    "error": 0,
                    "audited": False,
                }),
                headers=[
                    ("Content-Type", "application/json")
                ],
            )

        callback_payload = self._decode_callback_token(
            dms_file,
            token,
        )

        if not callback_payload:
            return request.make_response(
                json.dumps({"error": 1}),
                headers=[
                    ("Content-Type", "application/json")
                ],
                status=403,
            )

        try:
            user_id = int(
                callback_payload.get("user_id", 0)
            )
        except (TypeError, ValueError):
            user_id = 0

        editor_user = (
            request.env["res.users"]
            .sudo()
            .browse(user_id)
        )

        if not editor_user.exists():
            return request.make_response(
                json.dumps({"error": 1}),
                headers=[
                    ("Content-Type", "application/json")
                ],
                status=403,
            )

        dms_file_as_editor = (
            dms_file
            .with_user(editor_user)
            .sudo()
        )

        dms_file_as_editor.message_post(
            body=_(
                "Document was edited in ONLYOFFICE "
                "and the editing session was left without saving."
            ),
            author_id=editor_user.partner_id.id,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

        _logger.info(
            "AUDIT: DMS file %s was edited and left "
            "without saving by user %s (%s).",
            file_id,
            editor_user.id,
            editor_user.name,
        )

        return request.make_response(
            json.dumps({"error": 0}),
            headers=[
                ("Content-Type", "application/json")
            ],
        )



    # OPEN EDITOR

    # ---------------------------------------------------------



    @http.route(

        "/document_editor/dms/open/<int:file_id>",

        type="http",

        auth="user",

        methods=["GET"],

    )

    def open_editor(

        self,

        file_id,

        **kwargs,

    ):

        dms_file = (

            request.env["dms.file"]

            .browse(file_id)

        )



        if not dms_file.exists():

            return request.not_found()



        filename = dms_file.name or ""



        file_info = self._get_office_file_info(

            filename

        )



        if not file_info:

            return request.make_response(

                _(

                    "ONLYOFFICE editing is currently "

                    "available for DOCX, XLSX, PPTX, "

                    "CSV, PDF and Markdown files."

                ),

                headers=[

                    (

                        "Content-Type",

                        "text/plain; charset=utf-8",

                    )

                ],

                status=400,

            )



        if not dms_file.permission_write:

            return request.make_response(

                _(

                    "You do not have permission "

                    "to edit this document."

                ),

                headers=[

                    (

                        "Content-Type",

                        "text/plain; charset=utf-8",

                    )

                ],

                status=403,

            )



        onlyoffice_url = self._get_parameter(

            "document_editor.onlyoffice_url",

            "http\://localhost:8080",

        )



        config_url = (

            f"/document_editor/dms/config/"

            f"{dms_file.id}"

        )



        dms_action = request.env.ref(

            "dms.action_dms_file"

        )



        return_url = (

            f"/odoo/action-{dms_action.id}/"

            f"{dms_file.id}"

        )



        return request.render(

            "document_editor.onlyoffice_editor_page",

            {

                "file": dms_file,

                "config_url": config_url,

                "onlyoffice_url": (

                    onlyoffice_url.rstrip("/")

                ),

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

    def editor_config(

        self,

        file_id,

        **kwargs,

    ):

        dms_file = (

            request.env["dms.file"]

            .browse(file_id)

        )



        if not dms_file.exists():

            return request.not_found()



        filename = dms_file.name or ""



        extension = self._get_file_extension(

            filename

        )



        file_info = self._get_office_file_info(

            filename

        )



        if not file_info:

            return request.make_response(

                json.dumps(

                    {

                        "error": (

                            "Only DOCX, XLSX, PPTX, "

                            "CSV, PDF and Markdown "

                            "files are supported."

                        )

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

            "http\://odoo20-web:8069",

        ).rstrip("/")



        # Token for ONLYOFFICE to download the file.

        content_token = self._make_token(

            dms_file

        )



        # Separate token for callbacks.

        callback_token = self._make_callback_token(

            dms_file

        )



        if not content_token or not callback_token:

            return request.make_response(

                json.dumps(

                    {

                        "error": (

                            "Unable to generate "

                            "document access or "

                            "callback token."

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

            f"/document_editor/dms/content/"

            f"{dms_file.id}"

            f"?token={quote(content_token)}"

        )



        callback_url = (

            f"{odoo_base_url}"

            f"/document_editor/dms/callback/"

            f"{dms_file.id}"

            f"?token={quote(callback_token)}"

        )

        unsaved_audit_url = (

            f"{odoo_base_url}"
            f"/document_editor/dms/unsaved-audit/"
            f"{dms_file.id}"
            f"?token={quote(callback_token)}"
            f"&initial_checksum={quote(dms_file.checksum or '')}"

)



        config = {

            "documentType": (

                file_info["document_type"]

            ),



            "document": {

                "fileType": extension,

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



                # Enable real-time co-editing.

                "coEditing": {

                    "mode": "fast",

                    "change": False,

                },



                "customization": {

                    "autosave": False,

                    "forcesave": True,

                    "savetitle": True,

                },



                "user": {

                    "id": str(

                        request.env.user.id

                    ),

                    "name": (

                        request.env.user.name

                        or "User"

                    ),

                },

            },

        }



        config["unsavedAuditUrl"] = unsaved_audit_url



        # PDF-specific option.

        #

        # Keep this disabled by default. A normal PDF is opened

        # directly in the PDF editor. Fillable PDFs can later use

        # isForm=True when required.

        if extension == "pdf":

            config["document"]["isForm"] = False



        config["token"] = jwt.encode(

            config,

            secret,

            algorithm="HS256",

        )



        _logger.info(

            "ONLYOFFICE config generated for DMS "

            "file %s (%s)",

            dms_file.id,

            file_info["label"],

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



        if not self._check_token(

            dms_file,

            token,

        ):

            return request.make_response(

                "Invalid token",

                status=403,

            )



        filename = dms_file.name or ""



        file_info = self._get_office_file_info(

            filename

        )



        if not file_info:

            return request.make_response(

                (

                    "Only DOCX, XLSX, PPTX, CSV, "

                    "PDF and Markdown files are supported."

                ),

                status=400,

            )



        binary = self._get_file_binary(

            dms_file

        )



        if not binary:

            return request.make_response(

                "File has no content.",

                status=404,

            )



        return request.make_response(

            binary,

            headers=[

                (

                    "Content-Type",

                    file_info["mimetype"],

                ),

                (

                    "Content-Disposition",

                    (

                        "inline; "

                        "filename*=UTF-8''"

                        f"{quote(filename)}"

                    ),

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



        callback_payload = (

            self._decode_callback_token(

                dms_file,

                token,

            )

        )



        if not callback_payload:

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



            callback_file_type = (

                (data.get("filetype") or "")

                .lower()

                .lstrip(".")

            )



            filename = dms_file.name or ""



            extension = self._get_file_extension(

                filename

            )



            file_info = self._get_office_file_info(

                filename

            )



            if not file_info:

                raise ValueError(

                    "Unsupported DMS document type."

                )



            _logger.info(

                "ONLYOFFICE callback for DMS file %s: "

                "status=%s, filetype=%s, "

                "forcesavetype=%s",

                file_id,

                status,

                callback_file_type or "unknown",

                data.get("forcesavetype"),

            )



            # -------------------------------------------------

            # Save after changes

            # -------------------------------------------------



            if status in (2, 6):

                edited_url = data.get("url")



                if not edited_url:

                    raise ValueError(

                        "ONLYOFFICE did not provide "

                        "an edited document URL."

                    )



                # ONLYOFFICE normally returns the original

                # format when assemblyFormatAsOrigin is enabled.

                #

                # We accept the native OOXML return for CSV and

                # log it clearly rather than silently storing an

                # XLSX binary inside a .csv file.

                if (

                    callback_file_type

                    and callback_file_type != extension

                ):

                    if extension == "csv":

                        _logger.warning(

                            "ONLYOFFICE returned %s for CSV "

                            "file %s. Attempting conversion "

                            "back to CSV is required.",

                            callback_file_type,

                            file_id,

                        )

                    elif extension == "md":

                        raise ValueError(

                            "ONLYOFFICE returned "

                            f"{callback_file_type} instead of "

                            "Markdown for {filename}. "

                            "Enable assemblyFormatAsOrigin "

                            "in ONLYOFFICE Docs."

                        )

                    elif extension == "pdf":

                        raise ValueError(

                            "ONLYOFFICE returned "

                            f"{callback_file_type} instead of "

                            f"PDF for {filename}."

                        )

                    else:

                        raise ValueError(

                            "ONLYOFFICE returned an unexpected "

                            f"file type: "

                            f"{callback_file_type}. "

                            f"Expected {extension}."

                        )



                download_url = (

                    self._get_onlyoffice_download_url(

                        edited_url

                    )

                )



                _logger.info(

                    "Downloading edited %s for DMS file %s "

                    "from ONLYOFFICE: %s",

                    file_info["label"],

                    file_id,

                    download_url,

                )



                response = requests.get(

                    download_url,

                    timeout=60,

                )



                response.raise_for_status()



                binary = response.content



                # -------------------------------------------------

                # Validate returned file

                # -------------------------------------------------



                returned_type = (

                    callback_file_type

                    or extension

                )



                returned_info = (

                    self.OFFICE_FILE_TYPES.get(

                        returned_type

                    )

                )



                # For CSV, ONLYOFFICE may return XLSX depending

                # on server original-format configuration.

                if (

                    extension == "csv"

                    and returned_type != "csv"

                ):

                    if returned_type != "xlsx":

                        raise ValueError(

                            "ONLYOFFICE returned an unsupported "

                            f"format ({returned_type}) while "

                            "saving a CSV file."

                        )



                    if not binary.startswith(b"PK"):

                        raise ValueError(

                            "ONLYOFFICE returned invalid XLSX "

                            "data for CSV conversion."

                        )



                    raise ValueError(

                        "CSV was opened successfully, but "

                        "ONLYOFFICE returned XLSX instead "

                        "of CSV. Enable "

                        "assemblyFormatAsOrigin in the "

                        "ONLYOFFICE server configuration "

                        "so the original CSV format is "

                        "returned on save."

                    )



                if not returned_info:

                    raise ValueError(

                        f"Unsupported returned file type: "

                        f"{returned_type}"

                    )



                self._validate_binary(

                    binary,

                    returned_info,

                    returned_type,

                )



                # -------------------------------------------------

                # CHECKSUM

                # -------------------------------------------------



                old_checksum = (

                    dms_file.checksum

                )



                new_checksum = (

                    dms_file._get_checksum(

                        binary

                    )

                )



                editor_user = (

                    self._get_editor_user(

                        data,

                        callback_payload,

                    )

                )



                # -------------------------------------------------

                # Nothing changed

                # -------------------------------------------------



                if old_checksum == new_checksum:

                    _logger.info(

                        "No content change detected for "

                        "DMS file %s; skipping audit.",

                        file_id,

                    )



                else:

                    dms_file_as_editor = (

                        dms_file

                        .with_user(editor_user)

                        .sudo()

                    )



                    dms_file_as_editor.write(

                        {

                            "content": (

                                base64.b64encode(

                                    binary

                                ).decode("ascii")

                            ),

                        }

                    )



                    saved_checksum = (

                        dms_file_as_editor.checksum

                    )



                    if (

                        saved_checksum

                        != old_checksum

                    ):

                        self._post_edit_audit(

                            dms_file_as_editor,

                            editor_user,

                        )



                        _logger.info(

                            "AUDIT: DMS file %s (%s) "

                            "modified by user %s (%s). "

                            "Checksum changed from %s to %s.",

                            file_id,

                            file_info["label"],

                            editor_user.id,

                            editor_user.name,

                            old_checksum,

                            saved_checksum,

                        )



                _logger.info(

                    "Successfully processed updated %s "

                    "for DMS file %s (%s bytes)",

                    file_info["label"],

                    file_id,

                    len(binary),

                )



            # -------------------------------------------------

            # Save errors

            # -------------------------------------------------



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
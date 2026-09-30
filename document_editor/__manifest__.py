{
    "name": "DMS ONLYOFFICE Document Editor",
    "version": "20.0.1.0.0",
    "category": "Documents",
    "summary": "Edit DOCX, XLSX and PPTX files from Odoo DMS using ONLYOFFICE",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "dms",
    ],
    "author": "Aayush Poudel",
    "data": [
        "views/editor_templates.xml",
        "views/dms_file_views.xml",
        "views/res_config_settings.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "document_editor/static/src/js/onlyoffice_editor.js",
        ],
    },
    "installable": True,
    "application": True,
}
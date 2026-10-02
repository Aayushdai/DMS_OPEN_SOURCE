// /** ********************************************************************************
//     Copyright 2024 Subteno - Timothée Vannier (https://www.subteno.com).
//     License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
//  **********************************************************************************/

import {BinaryField} from "@web/views/fields/binary/binary_field";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {standardFieldProps} from "@web/views/fields/standard_field_props";
import {useFileViewer} from "@web/core/file_viewer/file_viewer_hook";
import {useService} from "@web/core/utils/hooks";

export class PreviewRecordField extends BinaryField {
    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.fileViewer = useFileViewer();
    }

    onFilePreview() {
        const fileId = this.props.record.resId;
        const filename = this.props.record.data.display_name || "";
        const extension = filename.includes(".")
            ? filename.split(".").pop().toLowerCase()
            : "";

        const onlyOfficeExtensions = new Set([
            "docx",
            "xlsx",
            "pptx",
            "csv",
            "pdf",
            "md",
        ]);

        if (onlyOfficeExtensions.has(extension)) {
            window.location.href = `/document_editor/dms/open/${fileId}`;
            return;
        }

        const attachment = this.store["ir.attachment"].insert({
            id: fileId,
            filename: filename,
            name: filename,
            mimetype: this.props.record.data.mimetype,
            model_name: this.props.record.resModel,
        });

        this.fileViewer.open(attachment);
    }
}

PreviewRecordField.template = "dms.FilePreviewField";

PreviewRecordField.props = {
    ...standardFieldProps,
};

const previewRecordField = {
    component: PreviewRecordField,
    displayName: _t("Preview Record"),
    supportedTypes: ["binary"],
    extractProps: () => {
        return {};
    },
};

registry.category("fields").add("preview_binary", previewRecordField);
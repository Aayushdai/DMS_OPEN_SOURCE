// /** ********************************************************************************
//     Copyright 2024 Subteno - Timothée Vannier (https://www.subteno.com).
//     License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
//  **********************************************************************************/
import {KanbanRecord} from "@web/views/kanban/kanban_record";
import {useFileViewer} from "@web/core/file_viewer/file_viewer_hook";
import {useService} from "@web/core/utils/hooks";

const videoReadableTypes = ["x-matroska", "mp4", "webm"];
const audioReadableTypes = ["mp3", "ogg", "wav", "aac", "mpa", "flac", "m4a"];
const onlyOfficeExtensions = ["docx", "xlsx", "pptx", "csv", "pdf", "md"];
export class FileKanbanRecord extends KanbanRecord {
    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.fileViewer = useFileViewer();
    }

    isVideo(mimetype) {
        return videoReadableTypes.includes(mimetype);
    }

    isAudio(mimetype) {
        return audioReadableTypes.includes(mimetype);
    }

    /**
     * @override
     *
     * Override to open the preview upon clicking the image, if compatible.
     */
    onGlobalClick(ev) {
    const self = this;

    if (ev.target.closest(".o_kanban_dms_file_preview")) {
        const filename = self.props.record.data.name || "";
        const extension = filename.includes(".")
            ? filename.split(".").pop().toLowerCase()
            : "";

        if (onlyOfficeExtensions.includes(extension)) {
            window.location.href =
                `/document_editor/dms/open/${self.props.record.data.id}`;
            return;
        }

        let mimetype = "";

        if (self.isVideo(extension)) {
            mimetype = `video/${extension}`;
        } else if (self.isAudio(extension)) {
            mimetype = "audio/mpeg";
        } else {
            mimetype = self.props.record.data.mimetype;
        }

        const attachment = this.store["ir.attachment"].insert({
            id: self.props.record.data.id,
            filename: filename,
            name: filename,
            mimetype: mimetype,
            model_name: self.props.record.resModel,
        });

        this.fileViewer.open(attachment);
        return;
    }

    return super.onGlobalClick(ev);
}
}

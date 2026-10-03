document.addEventListener("DOMContentLoaded", async () => {
    const container = document.getElementById("onlyoffice-editor");
    const backButton = document.getElementById("back-to-odoo");

    let docEditor = null;
    let hasUnsavedChanges = false;
    let auditSent = false;

    const getReturnUrl = () => {
        return backButton?.dataset.returnUrl || "";
    };

    if (!container) {
        return;
    }

    const configUrl = container.dataset.configUrl;

    try {
        const response = await fetch(configUrl);

        if (!response.ok) {
            throw new Error(
                `Config request failed: ${response.status}`
            );
        }

        const config = await response.json();

        if (config.error) {
            throw new Error(config.error);
        }

        if (typeof DocsAPI === "undefined") {
            throw new Error(
                "ONLYOFFICE DocsAPI is not available."
            );
        }

        const sendUnsavedAudit = () => {
            if (!hasUnsavedChanges || auditSent) {
                return;
            }

            const auditUrl = config.unsavedAuditUrl;

            if (!auditUrl) {
                console.error(
                    "Unsaved audit URL is missing."
                );
                return;
            }

            auditSent = true;

            const payload = JSON.stringify({
                event: "unsaved_edit",
            });

            const blob = new Blob(
                [payload],
                {
                    type: "application/json",
                }
            );

            const beaconSent = navigator.sendBeacon(
                auditUrl,
                blob
            );

            if (!beaconSent) {
                fetch(auditUrl, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: payload,
                    keepalive: true,
                }).catch((error) => {
                    console.error(
                        "Unsaved audit request failed:",
                        error
                    );
                });
            }
        };

        // Make sure the events object exists.
        config.events = config.events || {};

        // Detect when the current user modifies the document.
        config.events.onDocumentStateChange = (event) => {
            hasUnsavedChanges = event.data === true;

            console.log(
                "ONLYOFFICE document changed:",
                hasUnsavedChanges
            );
        };

        // Called after ONLYOFFICE confirms that the editor
        // should be closed.
        config.events.onRequestClose = () => {
            sendUnsavedAudit();

            const returnUrl = getReturnUrl();

            if (!returnUrl) {
                console.error("Back URL is missing.");
                return;
            }

            window.location.href = returnUrl;
        };

        // Enable ONLYOFFICE's own close button.
        config.editorConfig = config.editorConfig || {};

        config.editorConfig.customization =
            config.editorConfig.customization || {};

        config.editorConfig.customization.close = {
            visible: true,
            text: "Close",
        };

        // Create the editor.
        docEditor = new DocsAPI.DocEditor(
            "onlyoffice-editor",
            config
        );

        // Do not navigate directly.
        // Let ONLYOFFICE check for unsaved changes first.
        if (backButton) {
            backButton.addEventListener("click", (event) => {
                event.preventDefault();

                const returnUrl = getReturnUrl();

                if (!returnUrl) {
                    console.error("Back URL is missing.");
                    return;
                }

                if (docEditor) {
                    docEditor.requestClose();
                } else {
                    window.location.href = returnUrl;
                }
            });
        }

    } catch (error) {
        console.error(
            "ONLYOFFICE initialization failed:",
            error
        );

        container.innerHTML = `
            <div style="padding: 30px; font-family: sans-serif;">
                <h2>Unable to open document</h2>
                <p>${error.message}</p>
            </div>
        `;
    }
});
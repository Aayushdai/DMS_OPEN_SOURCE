document.addEventListener("DOMContentLoaded", async () => {
    const container = document.getElementById("onlyoffice-editor");
    const backButton = document.getElementById("back-to-odoo");

    let docEditor = null;

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

        // Make sure the events object exists.
        config.events = config.events || {};

        // Called by ONLYOFFICE after the user confirms closing.
        config.events.onRequestClose = () => {
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

        // IMPORTANT:
        // Do not directly navigate away here.
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
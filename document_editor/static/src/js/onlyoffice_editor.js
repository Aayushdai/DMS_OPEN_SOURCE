document.addEventListener("DOMContentLoaded", async () => {
    const container = document.getElementById("onlyoffice-editor");
    const backButton = document.getElementById("back-to-odoo");

    if (backButton) {
        backButton.addEventListener("click", () => {
            const returnUrl = backButton.dataset.returnUrl;

            console.log("Back to Odoo:", returnUrl);

            if (!returnUrl) {
                console.error("Back URL is missing.");
                return;
            }

            window.location.href = returnUrl;
        });
    }

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

        new DocsAPI.DocEditor(
            "onlyoffice-editor",
            config
        );

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
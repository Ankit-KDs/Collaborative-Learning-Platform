/**
 * AI-Powered Collaborative Learning Platform
 * Main client-side script
 */

document.addEventListener("DOMContentLoaded", () => {
    // Propagate per-tab session token across GET/POST forms and internal links
    const tabId = window.__COLLABLEARN_TAB_ID__;
    if (tabId) {
        const ensureFormTab = (form) => {
            try {
                const actionAttr = form.getAttribute("action");
                if (actionAttr) {
                    const parsed = new URL(actionAttr, window.location.origin);
                    if (parsed.origin !== window.location.origin) return;
                    if (parsed.searchParams.get("_tab") !== tabId) {
                        parsed.searchParams.set("_tab", tabId);
                        form.setAttribute("action", parsed.pathname + parsed.search + parsed.hash);
                    }
                }
                const method = (form.getAttribute("method") || "GET").toUpperCase();
                if (method === "GET") {
                    let hidden = form.querySelector('input[name="_tab"]');
                    if (!hidden) {
                        hidden = document.createElement("input");
                        hidden.type = "hidden";
                        hidden.name = "_tab";
                        form.appendChild(hidden);
                    }
                    hidden.value = tabId;
                }
            } catch (e) {}
        };

        document.querySelectorAll("form").forEach(ensureFormTab);
        document.addEventListener("submit", (e) => {
            if (e.target && e.target.tagName === "FORM") {
                ensureFormTab(e.target);
            }
        }, true);

        document.addEventListener("click", (e) => {
            if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
                return;
            }
            const link = e.target.closest ? e.target.closest("a[href]") : null;
            if (!link) return;
            if (link.target === "_blank" || link.hasAttribute("download")) return;
            const rawHref = link.getAttribute("href") || "";
            if (!rawHref || rawHref.startsWith("#") || rawHref.startsWith("javascript:") || rawHref.startsWith("mailto:")) {
                return;
            }
            try {
                const parsed = new URL(link.href, window.location.origin);
                if (parsed.origin === window.location.origin && parsed.searchParams.get("_tab") !== tabId) {
                    parsed.searchParams.set("_tab", tabId);
                    link.href = parsed.toString();
                }
            } catch (e) {}
        }, true);
    }

    // Auto-dismiss alert messages after 6 seconds
    const alerts = document.querySelectorAll(".alert-dismissible");
    alerts.forEach((alert) => {
        setTimeout(() => {
            try {
                const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                bsAlert.close();
            } catch (e) {
                // If bootstrap is not loaded yet or alert is already closed
            }
        }, 6000);
    });

    // Initialize Bootstrap tooltips if any
    const tooltipTriggerList = [].slice.call(
        document.querySelectorAll('[data-bs-toggle="tooltip"]')
    );
    tooltipTriggerList.map((tooltipTriggerEl) => {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Prevent double submissions and show subtle loading spinner on form submit
    const forms = document.querySelectorAll("form:not(.no-auto-disable)");
    forms.forEach((form) => {
        form.addEventListener("submit", function (e) {
            // Check form validation if supported
            if (this.checkValidity && !this.checkValidity()) {
                return;
            }

            const submitBtn = this.querySelector('button[type="submit"]:not(.no-disable)');
            if (submitBtn && !submitBtn.disabled) {
                // Delay disabling slightly so browser registers which button was clicked
                setTimeout(() => {
                    submitBtn.disabled = true;
                    submitBtn.dataset.originalContent = submitBtn.innerHTML;
                    submitBtn.innerHTML = `
                        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                        <span>Processing...</span>
                    `;
                }, 40);
            }
        });
    });
});

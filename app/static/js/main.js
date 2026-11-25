/**
 * AI-Powered Collaborative Learning Platform
 * Main client-side script
 */

document.addEventListener("DOMContentLoaded", () => {
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

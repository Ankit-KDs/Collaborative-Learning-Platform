/**
 * AI-Powered Collaborative Learning Platform
 * Real-Time 1-to-1 Polling Chat Controller
 *
 * Security & Reliability Features:
 * - XSS Prevention: Always uses DOM textContent for message rendering.
 * - CSRF Protected: Injects X-CSRFToken header in fetch requests.
 * - Resource Efficient: Pauses polling on tab blur/hidden via document.visibilityState.
 * - Smart Scroll: Auto-scrolls only if user is already near the bottom.
 */

document.addEventListener("DOMContentLoaded", () => {
    const container = document.getElementById("chatMessagesContainer");
    if (!container) return; // Exit if not on chat room page

    const roomId = container.getAttribute("data-room-id");
    const currentUserId = parseInt(container.getAttribute("data-current-user-id"), 10);
    const isGroup = container.getAttribute("data-is-group") === "true";
    let afterId = parseInt(container.getAttribute("data-after-id") || "0", 10);

    const chatForm = document.getElementById("chatForm");
    const textInput = document.getElementById("chatTextInput");
    const imageInput = document.getElementById("chatImageInput");
    const attachBtn = document.getElementById("attachBtn");
    const sendBtn = document.getElementById("sendBtn");

    const imagePreviewBar = document.getElementById("imagePreviewBar");
    const previewFilename = document.getElementById("previewFilename");
    const previewFilesize = document.getElementById("previewFilesize");
    const clearImageBtn = document.getElementById("clearImageBtn");

    const errorAlert = document.getElementById("chatErrorAlert");
    const errorMessage = document.getElementById("chatErrorMessage");
    const warningAlert = document.getElementById("chatWarningAlert");
    const warningMessage = document.getElementById("chatWarningMessage");
    const emptyNotice = document.getElementById("emptyChatNotice");

    // Extract CSRF token from meta tag
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";

    let pollTimer = null;
    let isPolling = false;

    // Helper: Scroll container to bottom
    const scrollToBottom = () => {
        container.scrollTop = container.scrollHeight;
    };

    // Helper: Check if user is scrolled near bottom (within 140px threshold)
    const isNearBottom = () => {
        const threshold = 140;
        return (container.scrollHeight - container.scrollTop - container.clientHeight) <= threshold;
    };

    // Initial scroll on load
    scrollToBottom();

    // Show inline chat error
    const showError = (msg) => {
        if (errorMessage && errorAlert) {
            errorMessage.textContent = msg;
            errorAlert.classList.remove("d-none");
        }
    };

    const clearError = () => {
        if (errorAlert) {
            errorAlert.classList.add("d-none");
        }
    };

    // Show gentle moderation warning
    const showWarning = (msg) => {
        if (warningMessage && warningAlert) {
            warningMessage.textContent = msg;
            warningAlert.classList.remove("d-none");
        } else {
            showError(msg);
        }
    };

    // Render a single message safely into the DOM without innerHTML for user text
    const appendMessage = (msg) => {
        if (emptyNotice) {
            emptyNotice.remove();
        }

        // Avoid duplicate message appending
        if (document.querySelector(`[data-message-id="${msg.id}"]`)) {
            return;
        }

        const shouldScroll = msg.is_self || isNearBottom();

        // System broadcast message rendering (e.g. joins, leaves, close events)
        if (msg.is_system) {
            const sysRow = document.createElement("div");
            sysRow.className = "text-center my-2";
            sysRow.setAttribute("data-message-id", msg.id);

            const sysBadge = document.createElement("span");
            sysBadge.className = "badge bg-secondary-subtle text-secondary px-3 py-1 rounded-pill small fst-italic border";
            sysBadge.textContent = msg.text;

            sysRow.appendChild(sysBadge);
            container.appendChild(sysRow);

            if (msg.id > afterId) {
                afterId = msg.id;
            }
            if (shouldScroll) {
                scrollToBottom();
            }
            return;
        }

        const row = document.createElement("div");
        row.className = `message-row ${msg.is_self ? "self" : "other"}`;
        row.setAttribute("data-message-id", msg.id);

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";

        // Sender name for peer messages in group rooms only
        if (isGroup && !msg.is_self && msg.sender_name) {
            const senderTag = document.createElement("div");
            senderTag.className = "fw-bold small mb-1 text-primary";
            senderTag.textContent = msg.sender_name;
            bubble.appendChild(senderTag);
        }

        // Attached image if present
        if (msg.image_url) {
            const imgWrap = document.createElement("div");
            imgWrap.className = "mb-1";

            const link = document.createElement("a");
            link.href = msg.image_url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";

            const img = document.createElement("img");
            img.src = msg.image_url;
            img.alt = "Attached photo";
            img.className = "chat-img-thumb border shadow-sm";
            img.loading = "lazy";

            link.appendChild(img);
            imgWrap.appendChild(link);
            bubble.appendChild(imgWrap);
        }

        // Message text - STRICT textContent to neutralize XSS
        if (msg.text && msg.text.trim().length > 0) {
            const textDiv = document.createElement("div");
            textDiv.className = "message-text";
            textDiv.textContent = msg.text;
            if (msg.text === "[message hidden pending review]") {
                textDiv.classList.add("text-muted", "fst-italic");
            }
            bubble.appendChild(textDiv);
        }

        const meta = document.createElement("div");
        meta.className = "message-meta d-flex align-items-center gap-2";

        const timeSpan = document.createElement("span");
        timeSpan.textContent = msg.created_at || "Just now";
        meta.appendChild(timeSpan);

        // Add report trigger for messages from other users
        if (!msg.is_self && !msg.is_system) {
            const reportBtn = document.createElement("button");
            reportBtn.type = "button";
            reportBtn.className = "btn btn-link btn-sm text-muted p-0 report-trigger-btn";
            reportBtn.title = "Report message";
            reportBtn.setAttribute("data-msg-id", msg.id);
            reportBtn.innerHTML = '<i class="bi bi-flag" style="font-size: 0.75rem;"></i>';
            meta.appendChild(reportBtn);
        }

        row.appendChild(bubble);
        row.appendChild(meta);
        container.appendChild(row);

        // Update high water mark
        if (msg.id > afterId) {
            afterId = msg.id;
        }

        if (shouldScroll) {
            scrollToBottom();
        }
    };

    // Polling function
    const fetchNewMessages = async () => {
        if (isPolling) return;
        isPolling = true;

        try {
            const response = await fetch(`/chats/${roomId}/messages?after_id=${afterId}`, {
                method: "GET",
                headers: {
                    "Accept": "application/json",
                },
            });

            if (response.ok) {
                const data = await response.json();
                if (data.messages && data.messages.length > 0) {
                    data.messages.forEach((msg) => appendMessage(msg));
                }

                // Update already-rendered messages if they have been hidden
                if (data.hidden_ids && data.hidden_ids.length > 0) {
                    data.hidden_ids.forEach((hid) => {
                        const targetRow = document.querySelector(`[data-message-id="${hid}"]`);
                        if (targetRow) {
                            const textEl = targetRow.querySelector(".message-text");
                            if (textEl && textEl.textContent !== "[message hidden pending review]") {
                                textEl.textContent = "[message hidden pending review]";
                                textEl.classList.add("text-muted", "fst-italic");
                            }
                        }
                    });
                }
            } else if (response.status === 403) {
                // Room closed or membership revoked
                stopPolling();
                showError("Chat session ended or access permission revoked.");
            }
        } catch (err) {
            // Network glitch; keep timer running silently
            console.warn("Polling network hiccup:", err);
        } finally {
            isPolling = false;
        }
    };

    // Start polling timer (every 3 seconds)
    const startPolling = () => {
        if (!pollTimer) {
            pollTimer = setInterval(fetchNewMessages, 3000);
        }
    };

    // Stop polling timer
    const stopPolling = () => {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    };

    // Tab visibility handling: pause polling when tab is hidden, resume on focus
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            stopPolling();
        } else {
            fetchNewMessages(); // Immediate check on tab return
            startPolling();
        }
    });

    startPolling();

    // Image Attachment Handlers
    attachBtn.addEventListener("click", () => {
        imageInput.click();
    });

    imageInput.addEventListener("change", () => {
        if (imageInput.files && imageInput.files[0]) {
            const file = imageInput.files[0];

            // Client-side quick size check (5MB)
            if (file.size > 5 * 1024 * 1024) {
                showError("The selected file exceeds 5MB. Please choose a smaller image.");
                imageInput.value = "";
                imagePreviewBar.classList.add("d-none");
                return;
            }

            clearError();
            previewFilename.textContent = file.name;
            const sizeInKb = Math.round(file.size / 1024);
            previewFilesize.textContent = `(${sizeInKb > 1024 ? (sizeInKb / 1024).toFixed(1) + " MB" : sizeInKb + " KB"})`;
            imagePreviewBar.classList.remove("d-none");
        } else {
            imagePreviewBar.classList.add("d-none");
        }
    });

    clearImageBtn.addEventListener("click", () => {
        imageInput.value = "";
        imagePreviewBar.classList.add("d-none");
    });

    // Form Submission (Send message via AJAX multipart)
    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        clearError();

        const textVal = textInput.value.trim();
        const hasFile = imageInput.files && imageInput.files.length > 0;

        if (!textVal && !hasFile) {
            showError("Please enter a text message or attach an image.");
            return;
        }

        const formData = new FormData();
        formData.append("text", textVal);
        if (hasFile) {
            formData.append("image", imageInput.files[0]);
        }

        // Disable send button while in-flight
        sendBtn.disabled = true;
        sendBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span> Sending...';

        try {
            const response = await fetch(`/chats/${roomId}/send`, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken,
                    "Accept": "application/json",
                },
                body: formData,
            });

            const data = await response.json();

            if (response.ok) {
                // Success: append message immediately to view
                appendMessage(data);

                // Reset inputs
                textInput.value = "";
                imageInput.value = "";
                imagePreviewBar.classList.add("d-none");
                scrollToBottom();
                textInput.focus();

                // Gentle moderation warning if message was masked
                if (data.warning) {
                    showWarning(data.warning);
                }
            } else {
                showError(data.error || "Failed to send message. Please try again.");
            }
        } catch (err) {
            showError("A network error occurred while sending your message. Please check your connection.");
        } finally {
            sendBtn.disabled = false;
            sendBtn.innerHTML = '<i class="bi bi-send-fill me-1"></i> Send';
        }
    });

    // Message Reporting Interactions
    container.addEventListener("click", (e) => {
        const btn = e.target.closest(".report-trigger-btn");
        if (btn) {
            const msgId = btn.getAttribute("data-msg-id");
            const modalEl = document.getElementById("reportMessageModal");
            const hiddenIdInput = document.getElementById("reportModalMessageId");
            const alertBox = document.getElementById("reportModalAlert");
            const noteInput = document.getElementById("reportModalNote");

            if (modalEl && hiddenIdInput) {
                hiddenIdInput.value = msgId;
                if (noteInput) noteInput.value = "";
                if (alertBox) {
                    alertBox.textContent = "";
                    alertBox.classList.add("d-none");
                }
                const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
                modal.show();
            }
        }
    });

    const reportForm = document.getElementById("reportMessageForm");
    if (reportForm) {
        reportForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const msgId = document.getElementById("reportModalMessageId").value;
            const reasonRadio = document.querySelector('input[name="reportReason"]:checked');
            const reason = reasonRadio ? reasonRadio.value : "other";
            const note = (document.getElementById("reportModalNote") ? document.getElementById("reportModalNote").value : "").trim();
            const alertBox = document.getElementById("reportModalAlert");
            const submitBtn = document.getElementById("submitReportBtn");

            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Submitting...';

            try {
                const response = await fetch(`/chats/${roomId}/messages/${msgId}/report`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken,
                        "Accept": "application/json",
                    },
                    body: JSON.stringify({ reason: reason, note: note }),
                });

                const data = await response.json();
                if (response.ok) {
                    const modalEl = document.getElementById("reportMessageModal");
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();

                    if (data.is_hidden) {
                        const targetRow = document.querySelector(`[data-message-id="${msgId}"]`);
                        if (targetRow) {
                            const textEl = targetRow.querySelector(".message-text");
                            if (textEl) {
                                textEl.textContent = "[message hidden pending review]";
                                textEl.classList.add("text-muted", "fst-italic");
                            }
                        }
                    }

                    showWarning(data.message || "Report submitted successfully.");
                } else {
                    if (alertBox) {
                        alertBox.textContent = data.error || "Failed to submit report.";
                        alertBox.classList.remove("d-none");
                    }
                }
            } catch (err) {
                if (alertBox) {
                    alertBox.textContent = "A network error occurred while submitting report.";
                    alertBox.classList.remove("d-none");
                }
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="bi bi-send-fill me-1"></i> Submit Report';
            }
        });
    }
});

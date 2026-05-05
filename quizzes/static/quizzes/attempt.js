(function () {
    const shell = document.querySelector(".attempt-shell");
    if (!shell) {
        return;
    }

    const gate = document.getElementById("fullscreen-gate");
    const attemptContent = document.getElementById("attempt-content");
    const forms = Array.from(document.querySelectorAll(".question-step"));
    const submitForm = document.getElementById("submit-form");
    const timer = document.getElementById("quiz-timer");
    const questionCounter = document.getElementById("question-counter");
    const questionProgress = document.getElementById("question-progress");
    const progressBar = questionProgress.querySelector(".progress-bar");
    const previousButton = document.getElementById("previous-question");
    const nextButton = document.getElementById("next-question");
    const fullscreenButton = document.getElementById("fullscreen-button");
    const fullscreenStatus = document.getElementById("fullscreen-status");
    const saveUrl = shell.dataset.saveUrl;
    const tabUrl = shell.dataset.tabUrl;
    const fullscreenUrl = shell.dataset.fullscreenUrl;
    const resultUrl = shell.dataset.resultUrl;
    const csrfToken = shell.querySelector("input[name='csrfmiddlewaretoken']").value;
    let remaining = parseInt(timer.dataset.remaining, 10);
    let currentPosition = Math.max(1, forms.findIndex(function (form) {
        return !form.classList.contains("d-none");
    }) + 1);
    let fullscreenExitCount = parseInt(shell.dataset.fullscreenExitCount || "0", 10);
    const fullscreenExitLimit = parseInt(shell.dataset.fullscreenExitLimit || "4", 10);
    let hasEnteredFullscreen = Boolean(document.fullscreenElement);
    let loggingFullscreenExit = false;
    let submitting = false;

    function lockAttempt() {
        gate.classList.remove("d-none");
        attemptContent.classList.add("d-none");
    }

    function unlockAttempt() {
        gate.classList.add("d-none");
        attemptContent.classList.remove("d-none");
    }

    function updateFullscreenStatus(message) {
        if (!fullscreenStatus) {
            return;
        }
        const prefix = message || "Fullscreen is required.";
        fullscreenStatus.querySelector("span").textContent = prefix + " Exits: " + fullscreenExitCount + "/" + fullscreenExitLimit + ". The quiz auto-submits after " + fullscreenExitLimit + " exits.";
    }

    function requestFullscreen() {
        const element = document.documentElement;
        if (!document.fullscreenElement && element.requestFullscreen) {
            element.requestFullscreen().catch(function () {});
        }
    }

    function postForm(url, data) {
        return fetch(url, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest"
            },
            body: data
        }).then(function (response) {
            return response.json();
        });
    }

    function redirectIfExpired(payload) {
        if (payload.expired) {
            window.location.href = payload.redirect_url || resultUrl;
            return true;
        }
        return false;
    }

    function showQuestion(position) {
        currentPosition = Math.min(Math.max(position, 1), forms.length);
        forms.forEach(function (form, index) {
            form.classList.toggle("d-none", index + 1 !== currentPosition);
        });
        questionCounter.textContent = "Question " + currentPosition + " of " + forms.length;
        questionProgress.setAttribute("aria-valuenow", String(currentPosition));
        progressBar.style.width = (currentPosition / forms.length * 100) + "%";
        previousButton.classList.toggle("d-none", currentPosition === 1);
        nextButton.classList.toggle("d-none", currentPosition === forms.length);
        window.history.replaceState(null, "", "/attempts/" + shell.dataset.attemptId + "/question/" + currentPosition + "/");
    }

    function logFullscreenExit() {
        if (loggingFullscreenExit || submitting) {
            return;
        }
        loggingFullscreenExit = true;
        postForm(fullscreenUrl, new FormData())
            .then(function (payload) {
                if (typeof payload.fullscreen_exit_count === "number") {
                    fullscreenExitCount = payload.fullscreen_exit_count;
                }
                updateFullscreenStatus("You exited fullscreen.");
                if (redirectIfExpired(payload)) {
                    return;
                }
                loggingFullscreenExit = false;
            })
            .catch(function () {
                updateFullscreenStatus("Fullscreen exit could not be logged. Re-enter fullscreen.");
                loggingFullscreenExit = false;
            });
    }

    function saveAnswer(form) {
        const selected = form.querySelector("input[name='option_id']:checked");
        const status = form.querySelector(".save-status");
        if (!selected || submitting) {
            return;
        }
        status.textContent = "Saving...";
        postForm(saveUrl, new FormData(form))
            .then(function (payload) {
                if (redirectIfExpired(payload)) {
                    return;
                }
                status.textContent = payload.saved ? "Saved" : "Could not save answer";
            })
            .catch(function () {
                status.textContent = "Save failed. The answer will retry when changed.";
            });
    }

    function formatTime(seconds) {
        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return String(minutes).padStart(2, "0") + ":" + String(secs).padStart(2, "0");
    }

    function tick() {
        timer.textContent = formatTime(Math.max(0, remaining));
        if (remaining <= 0) {
            submitting = true;
            submitForm.submit();
            return;
        }
        remaining -= 1;
        window.setTimeout(tick, 1000);
    }

    document.addEventListener("copy", function (event) {
        event.preventDefault();
    });
    document.addEventListener("paste", function (event) {
        event.preventDefault();
    });
    document.addEventListener("contextmenu", function (event) {
        event.preventDefault();
    });

    document.addEventListener("visibilitychange", function () {
        if (document.hidden && !submitting) {
            postForm(tabUrl, new FormData()).then(redirectIfExpired).catch(function () {});
        }
    });

    document.addEventListener("fullscreenchange", function () {
        if (document.fullscreenElement) {
            hasEnteredFullscreen = true;
            unlockAttempt();
            updateFullscreenStatus("Fullscreen enabled.");
            return;
        }

        lockAttempt();
        updateFullscreenStatus("Fullscreen is off.");
        if (hasEnteredFullscreen && !submitting) {
            logFullscreenExit();
        }
    });

    forms.forEach(function (form) {
        form.querySelectorAll("input[name='option_id']").forEach(function (input) {
            input.addEventListener("change", function () {
                saveAnswer(form);
            });
        });
    });

    previousButton.addEventListener("click", function () {
        showQuestion(currentPosition - 1);
    });

    nextButton.addEventListener("click", function () {
        showQuestion(currentPosition + 1);
    });

    fullscreenButton.addEventListener("click", requestFullscreen);
    submitForm.addEventListener("submit", function () {
        submitting = true;
    });

    showQuestion(currentPosition);
    updateFullscreenStatus(document.fullscreenElement ? "Fullscreen enabled." : "Fullscreen is off.");
    if (document.fullscreenElement) {
        unlockAttempt();
    } else {
        lockAttempt();
    }
    tick();
})();

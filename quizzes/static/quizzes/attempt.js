(function () {
    const shell = document.querySelector(".attempt-shell");
    if (!shell) {
        return;
    }

    const form = document.getElementById("answer-form");
    const submitForm = document.getElementById("submit-form");
    const status = document.getElementById("save-status");
    const timer = document.getElementById("quiz-timer");
    const fullscreenButton = document.getElementById("fullscreen-button");
    const saveUrl = shell.dataset.saveUrl;
    const tabUrl = shell.dataset.tabUrl;
    const resultUrl = shell.dataset.resultUrl;
    const csrfToken = form.querySelector("input[name='csrfmiddlewaretoken']").value;
    let remaining = parseInt(timer.dataset.remaining, 10);
    let submitting = false;

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

    function saveAnswer() {
        const selected = form.querySelector("input[name='option_id']:checked");
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
        if (!document.fullscreenElement && !submitting) {
            fullscreenButton.classList.remove("d-none");
        }
    });

    form.querySelectorAll("input[name='option_id']").forEach(function (input) {
        input.addEventListener("change", saveAnswer);
    });

    fullscreenButton.addEventListener("click", requestFullscreen);
    submitForm.addEventListener("submit", function () {
        submitting = true;
    });

    requestFullscreen();
    tick();
})();

/*
 * Kuraigal.TN — Government Portal front-end helpers
 * Handles: animated counters, navbar scroll shadow, FAB ripple,
 * toast notifications, and font-size accessibility controls.
 * Loaded on every page (see base.html).
 */
(function () {
    "use strict";

    /* ---------------- Navbar scroll shadow ---------------- */
    var navbar = document.querySelector(".gov-navbar");
    if (navbar) {
        var onScroll = function () {
            navbar.classList.toggle("scrolled", window.scrollY > 8);
        };
        window.addEventListener("scroll", onScroll, { passive: true });
        onScroll();
    }

    /* ---------------- Animated counters ---------------- */
    // Any element with [data-counter="123"] counts up from 0 to 123 when it
    // scrolls into view. Used on the homepage / dashboard stat cards.
    var counters = document.querySelectorAll("[data-counter]");
    if (counters.length) {
        var animateCounter = function (el) {
            var target = parseInt(el.getAttribute("data-counter"), 10) || 0;
            var duration = 1200; // ms
            var startTime = null;

            function step(timestamp) {
                if (!startTime) startTime = timestamp;
                var progress = Math.min((timestamp - startTime) / duration, 1);
                var eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
                el.textContent = Math.floor(eased * target).toLocaleString();
                if (progress < 1) {
                    window.requestAnimationFrame(step);
                } else {
                    el.textContent = target.toLocaleString();
                }
            }
            window.requestAnimationFrame(step);
        };

        if ("IntersectionObserver" in window) {
            var observer = new IntersectionObserver(
                function (entries) {
                    entries.forEach(function (entry) {
                        if (entry.isIntersecting) {
                            animateCounter(entry.target);
                            observer.unobserve(entry.target);
                        }
                    });
                },
                { threshold: 0.35 }
            );
            counters.forEach(function (el) { observer.observe(el); });
        } else {
            counters.forEach(animateCounter);
        }
    }

    /* ---------------- Floating Action Button ripple ---------------- */
    var fab = document.querySelector(".fab-report");
    if (fab) {
        fab.addEventListener("click", function (e) {
            var rect = fab.getBoundingClientRect();
            var ripple = document.createElement("span");
            var size = Math.max(rect.width, rect.height);
            ripple.className = "ripple";
            ripple.style.width = ripple.style.height = size + "px";
            ripple.style.left = (e.clientX - rect.left - size / 2) + "px";
            ripple.style.top = (e.clientY - rect.top - size / 2) + "px";
            fab.appendChild(ripple);
            window.setTimeout(function () { ripple.remove(); }, 650);
        });
    }

    /* ---------------- Toast helper ---------------- */
    // Usage: window.govToast("Saved successfully", "success" | "danger" | "warning" | "info")
    window.govToast = function (message, variant) {
        variant = variant || "info";
        var container = document.getElementById("gov-toast-container");
        if (!container) return;

        var wrapper = document.createElement("div");
        wrapper.className = "toast align-items-center text-bg-" + variant + " border-0";
        wrapper.setAttribute("role", "alert");
        wrapper.setAttribute("aria-live", "assertive");
        wrapper.setAttribute("aria-atomic", "true");
        wrapper.innerHTML =
            '<div class="d-flex">' +
            '<div class="toast-body">' + message + "</div>" +
            '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>' +
            "</div>";
        container.appendChild(wrapper);

        if (window.bootstrap && window.bootstrap.Toast) {
            var toast = new window.bootstrap.Toast(wrapper, { delay: 4000 });
            toast.show();
            wrapper.addEventListener("hidden.bs.toast", function () { wrapper.remove(); });
        }
    };

    // Auto-toast any Django messages rendered with [data-toast] on load.
    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-toast]").forEach(function (el) {
            window.govToast(el.getAttribute("data-toast"), el.getAttribute("data-toast-variant") || "info");
        });
    });

    /* ---------------- Accessibility: font size controls ---------------- */
    // Buttons with [data-font-step="1"] / [data-font-step="-1"] adjust root font size.
    var FONT_KEY = "gov-font-scale";
    var root = document.documentElement;

    function applyFontScale(scale) {
        root.style.fontSize = scale + "%";
    }
    var savedScale = parseInt(localStorage.getItem(FONT_KEY), 10) || 100;
    applyFontScale(savedScale);

    document.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-font-step]");
        if (!btn) return;
        var step = parseInt(btn.getAttribute("data-font-step"), 10);
        savedScale = Math.min(130, Math.max(85, savedScale + step * 5));
        applyFontScale(savedScale);
        localStorage.setItem(FONT_KEY, savedScale);
    });

    /* ---------------- High contrast toggle ---------------- */
    var CONTRAST_KEY = "gov-high-contrast";
    if (localStorage.getItem(CONTRAST_KEY) === "1") {
        document.body.classList.add("high-contrast");
    }
    document.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-toggle-contrast]");
        if (!btn) return;
        var active = document.body.classList.toggle("high-contrast");
        localStorage.setItem(CONTRAST_KEY, active ? "1" : "0");
    });

    /* ---------------- PWA: Service Worker registration (Phase 8) ---------------- */
    // Registered from site root ("/service-worker.js") so its scope covers every
    // page, not just /static/ - lets the app work offline and be "installed".
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", function () {
            navigator.serviceWorker.register("/service-worker.js").catch(function () {
                // Offline support just won't be available - not fatal, app still works online.
            });
        });
    }

    /* ---------------- Browser Notification alerts (Phase 8) ---------------- */
    // Polls the server every 30s for unread notifications and, if the user has
    // granted permission, shows a native browser notification for new ones.
    // This is a real, working notification feature - client-polled rather than
    // server-push, since server push needs external infrastructure (VAPID/FCM)
    // beyond a plain Django app.
    var notifyBtn = document.querySelector("[data-enable-push]");
    var NOTIF_SEEN_KEY = "gov-last-notif-count";

    function pollNotifications() {
        var pollUrl = document.body.getAttribute("data-notifications-poll-url");
        if (!pollUrl || Notification.permission !== "granted") return;

        fetch(pollUrl)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                var lastSeen = parseInt(localStorage.getItem(NOTIF_SEEN_KEY) || "0", 10);
                if (data.count > lastSeen && data.latest.length) {
                    var newest = data.latest[0];
                    new Notification("Kuraigal.TN", {
                        body: newest.message,
                        icon: "/static/img/icon-192.png"
                    });
                }
                localStorage.setItem(NOTIF_SEEN_KEY, data.count);
            })
            .catch(function () {});
    }

    if (notifyBtn && "Notification" in window) {
        if (Notification.permission === "granted") {
            notifyBtn.classList.add("d-none");
        }
        notifyBtn.addEventListener("click", function () {
            Notification.requestPermission().then(function (permission) {
                if (permission === "granted") {
                    notifyBtn.classList.add("d-none");
                    if (window.govToast) { window.govToast("Notifications enabled!", "success"); }
                }
            });
        });
    }
    if ("Notification" in window && document.body.getAttribute("data-notifications-poll-url")) {
        pollNotifications();
        setInterval(pollNotifications, 30000);
    }
})();

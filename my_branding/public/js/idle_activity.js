/* Nexum Air idle screen lock — activity reporter for pages outside the desk.
 *
 * Injected by my_branding.idle_lock.inject_activity_reporter into every non-desk page a
 * desk user opens (HR/CRM/Helpdesk and the other SPAs, /banking, web forms, /me, print
 * views). These pages show no warning or lock UI, but working in them must count as
 * activity, so a desk tab in the background doesn't lock the shared session mid-task.
 * Same shared clock, events and heartbeat as the desk's idle_lock.js. Wrapped so it can
 * never break the host page. */
(function () {
	try {
		var cfg = window.__NEXUM_IDLE__ || {};
		var KEY_LAST = "nexum-idle:last";
		var KEY_GEN = "nexum-idle:gen"; // a desk tab bumps it after every in-place unlock
		var BEAT_MS = 60 * 1000;
		var lastWrite = 0;
		var lastBeat = 0;
		var timer = null;
		var pending = false;
		var refreshing = false;

		function cookie(name) {
			var parts = (document.cookie || "").split(/;\s*/);
			for (var i = 0; i < parts.length; i++) {
				var eq = parts[i].indexOf("=");
				if (eq > 0 && parts[i].slice(0, eq) === name) {
					try {
						return decodeURIComponent(parts[i].slice(eq + 1));
					} catch (err) {
						return null;
					}
				}
			}
			return null;
		}

		// The user this page was opened for: Frappe sets user_id on every signed-in
		// response. A new token is only ever taken for this same user.
		var pageUser = cookie("user_id");

		function token() {
			var candidates = [window.csrf_token, window.frappe && window.frappe.csrf_token, cfg.csrf];
			for (var i = 0; i < candidates.length; i++) {
				var t = candidates[i];
				if (t && String(t).indexOf("{{") === -1 && t !== "None") return t;
			}
			return null;
		}

		// Unlocking in a desk tab (or signing in again in another tab) starts a new session
		// with a new CSRF token while this page still holds the old one: every heartbeat
		// then fails with 400, so the server ends the new session as idle while the user
		// works here, and the page's own saves fail too. Fetch the current token, for the
		// same user only (never carry on as someone else), and hand it to the page.
		function refreshToken(retry) {
			if (refreshing || !pageUser) return;
			refreshing = true;
			var stale = token();
			fetch("/api/method/my_branding.idle_lock.session_token", {
				credentials: "same-origin",
				headers: { Accept: "application/json" },
			})
				.then(function (r) {
					return r.ok ? r.json() : null;
				})
				.then(function (body) {
					var m = (body && body.message) || {};
					if (m.user !== pageUser || !m.csrf_token || m.csrf_token === stale) return;
					// Only the copies that still hold the stale token: frappe-ui reads
					// window.csrf_token on every call, so the page's own requests recover too.
					if (window.csrf_token === stale) window.csrf_token = m.csrf_token;
					if (window.frappe && window.frappe.csrf_token === stale) window.frappe.csrf_token = m.csrf_token;
					if (cfg.csrf === stale) cfg.csrf = m.csrf_token;
					if (retry) beat();
				})
				.catch(function () {
					/* offline: the next failed heartbeat tries again */
				})
				.then(function () {
					refreshing = false;
				});
		}

		function beat() {
			pending = false;
			lastBeat = Date.now();
			var t = token();
			if (!t) return;
			fetch("/api/method/my_branding.idle_lock.heartbeat", {
				method: "POST",
				credentials: "same-origin",
				headers: { Accept: "application/json", "X-Frappe-CSRF-Token": t },
			})
				.then(function (r) {
					if (r.status === 400) refreshToken(true); // stale CSRF token: a new session began elsewhere
				})
				.catch(function () {
					/* offline */
				});
		}

		function onActivity(e) {
			if (e && e.isTrusted === false) return; // ignore script-made events
			var t = Date.now();
			if (t - lastWrite >= 1000) {
				lastWrite = t;
				try {
					localStorage.setItem(KEY_LAST, String(t));
				} catch (err) {
					/* storage blocked */
				}
			}
			var wait = lastBeat + BEAT_MS - t;
			if (wait <= 0) {
				beat();
				return;
			}
			pending = true;
			if (!timer) {
				timer = setTimeout(function () {
					timer = null;
					if (pending) beat();
				}, wait);
			}
		}

		["mousemove", "mousedown", "keydown", "touchstart", "wheel"].forEach(function (name) {
			document.addEventListener(name, onActivity, { capture: true, passive: true });
		});
		// A desk tab just unlocked in place: take the new token now, before the next
		// heartbeat or save fails with it.
		window.addEventListener("storage", function (e) {
			if (e.key === KEY_GEN && e.newValue) refreshToken(false);
		});
	} catch (e) {
		/* never break the host page */
	}
})();

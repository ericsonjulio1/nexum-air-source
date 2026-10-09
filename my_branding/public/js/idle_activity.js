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
		var BEAT_MS = 60 * 1000;
		var lastWrite = 0;
		var lastBeat = 0;
		var timer = null;
		var pending = false;

		function token() {
			var candidates = [window.csrf_token, window.frappe && window.frappe.csrf_token, cfg.csrf];
			for (var i = 0; i < candidates.length; i++) {
				var t = candidates[i];
				if (t && String(t).indexOf("{{") === -1 && t !== "None") return t;
			}
			return null;
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
			}).catch(function () {
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
	} catch (e) {
		/* never break the host page */
	}
})();

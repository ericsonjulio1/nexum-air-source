/* Nexum Air idle screen lock — the desk half (server half: my_branding/idle_lock.py).
 * Spec: docs/superpowers/specs/2026-10-06-idle-screen-lock-design.md
 *
 * After `idle_minutes` with no mouse/keyboard/touch/wheel activity in ANY tab, every
 * desk tab shows a 60-second "Still there?" warning that only Continue dismisses. With
 * no answer the session is ended on the server and the page is locked IN PLACE —
 * blurred and inert, unsaved entries kept — until the same user re-enters the password
 * (and the authenticator code where two-factor is on). Every other way a session can
 * end is routed to the same lock instead of Frappe's redirect to /login.
 *
 * Tabs share one activity clock (localStorage) and tell each other about warn /
 * continue / lock / unlock (BroadcastChannel). Wrapped so a failure can never break
 * the desk. */
(function () {
	"use strict";
	if (!window.frappe || !frappe.Application) return;

	var KEY_LAST = "nexum-idle:last";
	var KEY_MSG = "nexum-idle:msg";
	var KEY_GEN = "nexum-idle:gen"; // bumped on every unlock: tabs that missed it refresh their token
	var KEY_LOGOUT = "nexum-idle:logout"; // when a tab last ended the session (one tab does it)
	var WARN_MS = 60 * 1000;
	var BEAT_MS = 60 * 1000;
	// Only events a person makes. No "scroll": pages scroll themselves (list refresh,
	// timelines), and wheel/touch/keys/mouse already cover every human scroll.
	var EVENTS = ["mousemove", "mousedown", "keydown", "touchstart", "wheel"];
	var LOGO = "/assets/my_branding/images/nexum-mark-white.png";

	var cfg = null;
	var user = null;
	var state = "off"; // off | active | warning | locked
	var localLast = Date.now();
	var lastWrite = 0;
	var warnAt = 0;
	var savedTitle = null;
	var lastBeat = 0;
	var beatTimer = null;
	var activitySinceBeat = false;
	var channel = null;
	var tmpId = null;
	var busy = false;
	var warnEl = null;
	var lockEl = null;
	var inertEls = [];
	var lateObserver = null;
	var myGen = 0;
	var refreshing = false;
	var confirming = false;
	var pendingLogout = null;

	// Every session-expiry path in frappe/request.js (401, 403-as-Guest,
	// r.session_expired) funnels through this method. This file loads before
	// frappe.start_app, so patching the prototype covers the very first instance.
	var nativeExpired = frappe.Application.prototype.handle_session_expired;
	frappe.Application.prototype.handle_session_expired = function () {
		if (state === "off") return nativeExpired.apply(this, arguments);
		confirmExpired();
	};

	function now() {
		return Date.now();
	}

	function esc(s) {
		return frappe.utils.escape_html(String(s == null ? "" : s));
	}

	function removeEl(el) {
		if (el && el.parentNode) el.parentNode.removeChild(el);
	}

	function setTitle(t) {
		if (savedTitle === null) savedTitle = document.title;
		document.title = t;
	}

	function restoreTitle() {
		if (savedTitle !== null) document.title = savedTitle;
		savedTitle = null;
	}

	// --- shared activity clock ---------------------------------------------------
	function readLast() {
		var shared = 0;
		try {
			shared = parseInt(localStorage.getItem(KEY_LAST), 10) || 0;
		} catch (e) {
			/* storage blocked: this tab keeps its own clock */
		}
		return Math.max(shared, localLast);
	}

	function writeLast(t) {
		localLast = t;
		try {
			localStorage.setItem(KEY_LAST, String(t));
		} catch (e) {
			/* storage blocked */
		}
	}

	function readGen() {
		try {
			return parseInt(localStorage.getItem(KEY_GEN), 10) || 0;
		} catch (e) {
			return 0;
		}
	}

	function writeGen(t) {
		try {
			localStorage.setItem(KEY_GEN, String(t));
		} catch (e) {
			/* storage blocked */
		}
	}

	// A tab that was frozen or asleep through an unlock still holds the deleted session's
	// CSRF token; fetch the current one (same user only) instead of failing every save.
	function refreshToken() {
		if (refreshing) return;
		refreshing = true;
		fetch("/api/method/my_branding.idle_lock.session_token", {
			credentials: "same-origin",
			headers: { Accept: "application/json" },
		})
			.then(function (r) {
				if (r.status === 401 || r.status === 403) {
					lock("server");
					return null;
				}
				return r.ok ? r.json() : null;
			})
			.then(function (body) {
				var m = (body && body.message) || {};
				if (!m.user) return;
				myGen = readGen();
				if (m.user === user && m.csrf_token) frappe.csrf_token = m.csrf_token;
				else lock("server"); // someone else signed in: never carry on as them
			})
			.catch(function () {
				/* offline: retried on the next tick */
			})
			.then(function () {
				refreshing = false;
			});
	}

	// A "signed out" answer can be stale: a request sent just before the lock may answer after
	// the user has already unlocked. Ask the server before locking, so a late reply never
	// re-locks a fresh session (and, through the broadcast, every other tab).
	function confirmExpired() {
		if (state === "locked" || state === "off" || confirming) return;
		confirming = true;
		fetch("/api/method/my_branding.idle_lock.session_token", {
			credentials: "same-origin",
			headers: { Accept: "application/json" },
		})
			.then(function (r) {
				if (!r.ok) {
					lock("server");
					return null;
				}
				return r.json();
			})
			.then(function (body) {
				var m = (body && body.message) || {};
				if (!body) return;
				if (m.user !== user) lock("server");
				else if (m.csrf_token) frappe.csrf_token = m.csrf_token; // still signed in
			})
			.catch(function () {
				lock("server"); // cannot confirm (offline): err on the side of locking
			})
			.then(function () {
				confirming = false;
			});
	}

	function broadcast(msg) {
		if (channel) {
			try {
				channel.postMessage(msg);
				return;
			} catch (e) {
				/* fall back to storage events */
			}
		}
		try {
			localStorage.setItem(KEY_MSG, JSON.stringify({ msg: msg, n: Math.random() }));
		} catch (e) {
			/* single tab */
		}
	}

	function onMessage(msg) {
		if (!msg || !msg.type) return;
		if (msg.type === "warn") showWarning(msg.at, true);
		else if (msg.type === "continue") onContinue(true);
		else if (msg.type === "lock") lock("remote", true);
		else if (msg.type === "unlock") afterLogin(true);
	}

	function onActivity(e) {
		if (state !== "active" || (e && e.isTrusted === false)) return; // ignore script-made events
		var t = now();
		activitySinceBeat = true;
		if (t - lastWrite >= 1000) {
			lastWrite = t;
			writeLast(t);
		}
		scheduleBeat();
	}

	// --- heartbeat (at most one a minute, only after real activity) -------------
	function scheduleBeat() {
		var wait = lastBeat + BEAT_MS - now();
		if (wait <= 0) {
			sendBeat();
			return;
		}
		if (beatTimer) return;
		beatTimer = setTimeout(function () {
			beatTimer = null;
			if (activitySinceBeat && state === "active") sendBeat();
		}, wait);
	}

	function sendBeat() {
		activitySinceBeat = false;
		lastBeat = now();
		fetch("/api/method/my_branding.idle_lock.heartbeat", {
			method: "POST",
			credentials: "same-origin",
			headers: { Accept: "application/json", "X-Frappe-CSRF-Token": frappe.csrf_token },
		})
			.then(function (r) {
				if (r.status === 401 || r.status === 403) confirmExpired();
				else if (r.status === 400) refreshToken(); // stale CSRF token (missed an unlock)
			})
			.catch(function () {
				/* offline: the one-second check still locks on time */
			});
	}

	// --- the one-second check ----------------------------------------------------
	function tick() {
		if (state !== "locked" && readGen() > myGen) refreshToken();
		if (state === "warning") {
			var left = Math.ceil((warnAt + WARN_MS - now()) / 1000);
			if (left <= 0) lock("idle");
			else setCountdown(left);
			return;
		}
		if (state !== "active") return;
		var idle = now() - readLast();
		var limit = cfg.idle_minutes * 60000;
		if (idle >= limit + WARN_MS) lock("idle"); // slept through the whole warning
		else if (idle >= limit) showWarning(now());
	}

	// --- warning -------------------------------------------------------------------
	function setCountdown(left) {
		var el = warnEl && warnEl.querySelector("#nx-idle-countdown");
		if (!el) return;
		var s = left % 60;
		el.textContent = Math.floor(left / 60) + ":" + (s < 10 ? "0" : "") + s;
	}

	function showWarning(at, remote) {
		if (state !== "active") return;
		state = "warning";
		warnAt = at || now();
		setTitle("⚠ " + __("Still there?"));
		warnEl = document.createElement("div");
		warnEl.id = "nx-idle-warning";
		warnEl.className = "nx-idle-root nx-idle-backdrop";
		warnEl.innerHTML =
			'<div class="nx-idle-card" role="alertdialog" aria-modal="true" aria-labelledby="nx-idle-warning-title">' +
			'<h2 id="nx-idle-warning-title" class="nx-idle-title">' + esc(__("Still there?")) + "</h2>" +
			'<p class="nx-idle-text">' + esc(__("For your security you will be signed out in")) +
			' <strong id="nx-idle-countdown"></strong></p>' +
			'<div class="nx-idle-actions">' +
			'<button type="button" id="nx-idle-logout" class="btn btn-default btn-sm">' + esc(__("Log out")) + "</button>" +
			'<button type="button" id="nx-idle-continue" class="btn btn-primary btn-sm">' + esc(__("Continue")) + "</button>" +
			"</div></div>";
		document.body.appendChild(warnEl);
		warnEl.querySelector("#nx-idle-continue").addEventListener("click", function () {
			onContinue(false);
		});
		warnEl.querySelector("#nx-idle-logout").addEventListener("click", signOut);
		setCountdown(Math.ceil((warnAt + WARN_MS - now()) / 1000));
		warnEl.querySelector("#nx-idle-continue").focus();
		if (!remote) broadcast({ type: "warn", at: warnAt });
	}

	function onContinue(remote) {
		if (state !== "warning") return;
		state = "active";
		removeEl(warnEl);
		warnEl = null;
		restoreTitle();
		localLast = now();
		if (!remote) {
			writeLast(localLast);
			broadcast({ type: "continue" });
			sendBeat();
		}
	}

	function signOut() {
		var go = function () {
			window.location.href = "/login";
		};
		fetch("/api/method/logout", {
			method: "POST",
			credentials: "same-origin",
			headers: { Accept: "application/json", "X-Frappe-CSRF-Token": frappe.csrf_token },
		}).then(go, go);
	}

	// --- lock ----------------------------------------------------------------------
	function lock(reason, remote) {
		if (state === "locked" || state === "off") return;
		state = "locked";
		removeEl(warnEl);
		warnEl = null;
		if (beatTimer) {
			clearTimeout(beatTimer);
			beatTimer = null;
		}
		restoreTitle();
		setTitle("🔒 " + __("Session locked"));
		buildLock();
		if (!remote) {
			broadcast({ type: "lock" });
			if (reason === "idle") endServerSession();
		}
	}

	// Logout and unlock must never overlap, across all tabs: a logout still in flight lands
	// after the new login and voids it. The Web Locks API gives one lock shared by every tab
	// on this site; the holder keeps it until its request completes.
	function withLogoutLock(fn) {
		if (navigator.locks && navigator.locks.request) {
			return navigator.locks.request("nexum-idle-logout", function () {
				return fn();
			});
		}
		return Promise.resolve().then(fn);
	}

	function endServerSession() {
		pendingLogout = withLogoutLock(function () {
			// Tabs that lock together must not each log out: the first one is enough.
			try {
				var last = parseInt(localStorage.getItem(KEY_LOGOUT), 10) || 0;
				if (now() - last < 15000) return null;
				localStorage.setItem(KEY_LOGOUT, String(now()));
			} catch (e) {
				/* storage blocked: this tab sends its own */
			}
			return fetch("/api/method/logout", {
				method: "POST",
				credentials: "same-origin",
				headers: { Accept: "application/json", "X-Frappe-CSRF-Token": frappe.csrf_token },
			}).catch(function () {
				/* offline: the server check ends the session on its own */
			});
		}).then(
			function () {
				pendingLogout = null;
			},
			function () {
				pendingLogout = null;
			}
		);
	}

	function buildLock() {
		var name = frappe.session.user_fullname || user;
		var email = frappe.session.user_email || user;
		lockEl = document.createElement("div");
		lockEl.id = "nx-idle-lock";
		lockEl.className = "nx-idle-root nx-idle-backdrop nx-idle-lock";
		lockEl.innerHTML =
			'<img class="nx-idle-logo" src="' + LOGO + '" alt="Nexum Air">' +
			'<form class="nx-idle-card" role="dialog" aria-modal="true" aria-labelledby="nx-idle-lock-title" novalidate>' +
			'<h2 id="nx-idle-lock-title" class="nx-idle-title">' + esc(__("Session locked")) + "</h2>" +
			'<p class="nx-idle-user"><strong>' + esc(name) + "</strong><br><span>" + esc(email) + "</span></p>" +
			'<input type="text" name="username" autocomplete="username" value="' + esc(user) + '" hidden>' +
			'<div class="nx-idle-step" data-step="password">' +
			'<label for="nx-idle-password" class="nx-idle-label">' + esc(__("Password")) + "</label>" +
			'<input id="nx-idle-password" type="password" class="form-control" autocomplete="current-password">' +
			"</div>" +
			'<div class="nx-idle-step" data-step="code" hidden>' +
			'<label for="nx-idle-code" class="nx-idle-label" id="nx-idle-prompt"></label>' +
			'<input id="nx-idle-code" type="text" class="form-control" inputmode="numeric" autocomplete="one-time-code">' +
			"</div>" +
			'<p id="nx-idle-error" class="nx-idle-error" role="alert"></p>' +
			'<p id="nx-idle-offline" class="nx-idle-text" hidden>' + esc(__("You're offline. Reconnect to unlock.")) + "</p>" +
			'<div class="nx-idle-actions">' +
			'<button type="button" id="nx-idle-signout" class="btn btn-default btn-sm">' + esc(__("Sign out / switch user")) + "</button>" +
			'<button type="submit" id="nx-idle-unlock" class="btn btn-primary btn-sm">' + esc(__("Unlock")) + "</button>" +
			"</div>" +
			'<p class="nx-idle-note">' + esc(__("Signing out discards unsaved changes on open pages.")) + "</p>" +
			"</form>";
		// Freeze the page behind: inert keeps clicks, focus and keys out of it.
		inertEls = [];
		Array.prototype.forEach.call(document.body.children, function (el) {
			if (el.classList.contains("nx-idle-root") || el.inert) return;
			el.inert = true;
			inertEls.push(el);
		});
		document.documentElement.classList.add("nx-idle-locked");
		document.body.appendChild(lockEl);
		// Dialogs opened after the lock (a failed save's message, a realtime event) must
		// be inert too, or Bootstrap's focus trap steals focus from the password field.
		if (typeof MutationObserver === "function") {
			lateObserver = new MutationObserver(function (records) {
				records.forEach(function (rec) {
					Array.prototype.forEach.call(rec.addedNodes, function (el) {
						if (el.nodeType !== 1 || el.classList.contains("nx-idle-root") || el.inert) return;
						el.inert = true;
						inertEls.push(el);
					});
				});
			});
			lateObserver.observe(document.body, { childList: true });
		}
		lockEl.querySelector("form").addEventListener("submit", function (e) {
			e.preventDefault();
			submitUnlock();
		});
		lockEl.querySelector("#nx-idle-signout").addEventListener("click", signOut);
		updateOnline();
		lockEl.querySelector("#nx-idle-password").focus();
	}

	function updateOnline() {
		if (!lockEl) return;
		var offline = navigator.onLine === false;
		lockEl.querySelector("#nx-idle-offline").hidden = !offline;
		lockEl.querySelector("#nx-idle-unlock").disabled = offline || busy;
	}

	function setBusy(b) {
		busy = b;
		updateOnline();
	}

	function showError(msg) {
		var el = lockEl && lockEl.querySelector("#nx-idle-error");
		if (el) el.textContent = msg || "";
	}

	// --- unlock --------------------------------------------------------------------
	function login(data) {
		return fetch("/api/method/login", {
			method: "POST",
			credentials: "same-origin",
			headers: {
				Accept: "application/json",
				"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
				"X-Frappe-CSRF-Token": frappe.csrf_token,
			},
			body: new URLSearchParams(data).toString(),
		}).then(function (r) {
			return r
				.json()
				.catch(function () {
					return {};
				})
				.then(function (body) {
					return { ok: r.ok, status: r.status, body: body };
				});
		});
	}

	function plainText(html) {
		// DOMParser documents never run scripts or load images.
		return new DOMParser().parseFromString(String(html), "text/html").body.textContent || "";
	}

	function errorMessage(body) {
		if (!body) return "";
		if (typeof body.message === "string" && body.message && body.message !== "Logged In") {
			return plainText(body.message);
		}
		try {
			var msgs = JSON.parse(body._server_messages || "[]");
			if (msgs.length) return plainText(JSON.parse(msgs[0]).message || "");
		} catch (e) {
			/* not a Frappe message list */
		}
		return "";
	}

	function showCodeStep(verification) {
		lockEl.querySelector('[data-step="password"]').hidden = true;
		lockEl.querySelector('[data-step="code"]').hidden = false;
		var prompt = verification && typeof verification.prompt === "string" && verification.prompt;
		lockEl.querySelector("#nx-idle-prompt").textContent =
			prompt || __("Enter the code from your authenticator app");
		var code = lockEl.querySelector("#nx-idle-code");
		code.value = "";
		code.focus();
	}

	function resetToPassword() {
		tmpId = null;
		lockEl.querySelector('[data-step="code"]').hidden = true;
		lockEl.querySelector('[data-step="password"]').hidden = false;
		var pwd = lockEl.querySelector("#nx-idle-password");
		pwd.value = "";
		pwd.focus();
	}

	function submitUnlock() {
		if (busy || navigator.onLine === false) return;
		var codeStep = !!tmpId;
		var input = lockEl.querySelector(codeStep ? "#nx-idle-code" : "#nx-idle-password");
		if (!(input.value || "").trim()) {
			showError(codeStep ? __("Enter the code.") : __("Enter your password."));
			return;
		}
		setBusy(true);
		showError("");
		var data = codeStep ? { tmp_id: tmpId, otp: input.value.trim() } : { usr: user, pwd: input.value };
		// A logout still in flight would land after the new login and void it: wait for this
		// tab's, and take the shared lock so no other tab's can overlap the login.
		(pendingLogout || Promise.resolve())
			.then(function () {
				return withLogoutLock(function () {
					return login(data);
				});
			})
			.then(function (res) {
				if (res.body && res.body.verification && res.body.tmp_id) {
					tmpId = res.body.tmp_id;
					showCodeStep(res.body.verification);
					setBusy(false);
					return;
				}
				var loggedIn = res.ok && res.body && (res.body.message === "Logged In" || res.body.home_page);
				if (!loggedIn) {
					// e.g. 401 wrong password, or 200 "Password Reset" (expired password: Frappe
					// e-mails a reset link and creates no session)
					var msg =
						res.body && res.body.message === "Password Reset"
							? __("Your password has expired. Check your email for a reset link.")
							: errorMessage(res.body) || __("Could not unlock. Check and try again.");
					if (codeStep && /expired/i.test(msg)) resetToPassword();
					showError(msg);
					setBusy(false);
					return;
				}
				return afterLogin(false);
			})
			.catch(function () {
				showError(__("Could not reach the server. Try again."));
				setBusy(false);
			});
	}

	function afterLogin(remote) {
		if (state !== "locked") return Promise.resolve();
		return fetch("/api/method/my_branding.idle_lock.session_token", {
			credentials: "same-origin",
			headers: { Accept: "application/json" },
		})
			.then(function (r) {
				if (!r.ok) {
					var err = new Error("session_token " + r.status);
					err.status = r.status;
					throw err;
				}
				return r.json();
			})
			.then(function (body) {
				var m = (body && body.message) || {};
				if (m.user !== user) {
					// Never unlock one user's page under another user's session.
					window.location.href = "/login";
					return;
				}
				frappe.csrf_token = m.csrf_token;
				if (!remote) writeGen(now());
				myGen = readGen();
				try {
					if (frappe.realtime && frappe.realtime.socket) frappe.realtime.socket.connect();
				} catch (e) {
					/* realtime is optional */
				}
				unlockUi();
				if (!remote) broadcast({ type: "unlock" });
			})
			.catch(function (err) {
				if (remote) return;
				if (err && (err.status === 401 || err.status === 403)) {
					// the new session was ended before this page could use it: just sign in again
					resetToPassword();
					showError(__("Please enter your password again."));
				} else {
					showError(__("Signed in, but the page could not reconnect. Reload to continue."));
				}
				setBusy(false);
			});
	}

	function unlockUi() {
		state = "active";
		tmpId = null;
		busy = false;
		localLast = now();
		lastWrite = 0;
		writeLast(localLast);
		lastBeat = now(); // the new session starts with a fresh activity record
		if (lateObserver) {
			lateObserver.disconnect();
			lateObserver = null;
		}
		inertEls.forEach(function (el) {
			el.inert = false;
		});
		inertEls = [];
		document.documentElement.classList.remove("nx-idle-locked");
		removeEl(lockEl);
		lockEl = null;
		restoreTitle();
	}

	// --- start ---------------------------------------------------------------------
	function init() {
		try {
			user = frappe.session && frappe.session.user;
			if (!user || user === "Guest") return;
			cfg = (frappe.boot && frappe.boot.nexum_idle_lock) || { enabled: true, idle_minutes: 3 };
			if (!cfg.enabled) return;
			cfg.idle_minutes = Math.max(1, Math.min(240, parseInt(cfg.idle_minutes, 10) || 3));
			state = "active";
			document.documentElement.setAttribute("data-nx-idle", "on"); // started (smoke tests wait on it)
			writeLast(now());
			EVENTS.forEach(function (name) {
				document.addEventListener(name, onActivity, { capture: true, passive: true });
			});
			if (typeof BroadcastChannel === "function") {
				channel = new BroadcastChannel("nexum-idle");
				channel.onmessage = function (e) {
					onMessage(e.data);
				};
			} else {
				window.addEventListener("storage", function (e) {
					if (e.key !== KEY_MSG || !e.newValue) return;
					try {
						onMessage(JSON.parse(e.newValue).msg);
					} catch (err) {
						/* ignore malformed messages */
					}
				});
			}
			myGen = readGen();
			window.addEventListener("pageshow", tick);
			window.addEventListener("online", updateOnline);
			window.addEventListener("offline", updateOnline);
			document.addEventListener("visibilitychange", function () {
				if (!document.hidden) tick();
			});
			setInterval(tick, 1000);
		} catch (e) {
			state = "off";
			console.error("[nexum idle lock] disabled:", e);
		}
	}

	$(document).on("app_ready", init);
})();

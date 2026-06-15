/* =============================================================================
   Nexum Air — split login page (left brand diagram + right credentials).
   Runs on web pages but acts ONLY on the login page (guards on #page-login),
   so it can never touch any other page. Adds body.nexum-login (login.css does
   the styling), injects the heading, and builds the animated left panel.
   No Frappe template edits -> survives app/Frappe updates.
   ============================================================================= */
(function () {
	var root = document.getElementById("page-login");
	if (!root) return; // not the login page
	if (document.querySelector(".nexum-art")) return; // already built
	document.body.classList.add("nexum-login");

	// ---- heading into the login card (replaces Frappe's "Login to X") ----
	var form = document.querySelector("form.form-login");
	if (form && form.parentNode && !form.parentNode.querySelector(".nexum-login-head")) {
		var head = document.createElement("div");
		head.className = "nexum-login-head";
		head.innerHTML = "<h1>Sign in to Nexum Air</h1><p>Your business application suite.</p>";
		form.parentNode.insertBefore(head, form);
	}

	// ---- left brand / diagram panel ----
	var logo = window.__NEXUM_LOGO__ || "/assets/my_branding/images/nexum-logo-notag.png";
	var svg =
		'<g fill="none">' +
		'<line class="link" x1="380" y1="248" x2="380" y2="80"/>' +
		'<line class="link" x1="494" y1="314" x2="640" y2="230"/>' +
		'<line class="link" x1="494" y1="446" x2="640" y2="530"/>' +
		'<line class="link" x1="380" y1="512" x2="380" y2="680"/>' +
		'<line class="link" x1="266" y1="446" x2="120" y2="530"/>' +
		'<line class="link" x1="266" y1="314" x2="120" y2="230"/>' +
		"</g>" +
		'<polygon class="ring" points="380,80 640,230 640,530 380,680 120,530 120,230"/>' +
		// travelling data dots flowing into the core
		'<circle class="spark" r="3.6"><animateMotion dur="4.2s" repeatCount="indefinite" path="M380,80 L380,380"/></circle>' +
		'<circle class="spark" r="3.6"><animateMotion dur="4.8s" begin="0.7s" repeatCount="indefinite" path="M640,230 L380,380"/></circle>' +
		'<circle class="spark" r="3.6"><animateMotion dur="4.0s" begin="1.4s" repeatCount="indefinite" path="M640,530 L380,380"/></circle>' +
		'<circle class="spark" r="3.6"><animateMotion dur="4.6s" begin="0.4s" repeatCount="indefinite" path="M380,680 L380,380"/></circle>' +
		'<circle class="spark" r="3.6"><animateMotion dur="4.3s" begin="1.1s" repeatCount="indefinite" path="M120,530 L380,380"/></circle>' +
		'<circle class="spark" r="3.6"><animateMotion dur="5.0s" begin="2.0s" repeatCount="indefinite" path="M120,230 L380,380"/></circle>' +
		// module nodes (icon only)
		'<g transform="translate(380,80)"><circle class="node-bg" r="46"/><g class="ico" transform="translate(-16,-15)"><line x1="0" y1="30" x2="32" y2="30"/><rect x="2" y="17" width="7" height="13"/><rect x="13" y="9" width="7" height="21"/><rect x="24" y="2" width="7" height="28"/></g></g>' +
		'<g transform="translate(640,230)"><circle class="node-bg" r="46"/><g class="ico" transform="translate(-17,-15)"><polyline points="0,28 12,15 20,21 34,4"/><polyline points="26,4 34,4 34,12"/></g></g>' +
		'<g transform="translate(640,530)"><circle class="node-bg" r="46"/><g class="ico" transform="translate(-17,-17)"><path d="M17 2 L33 11 L33 26 L17 35 L1 26 L1 11 Z"/><path d="M1 11 L17 20 L33 11 M17 20 L17 35"/></g></g>' +
		'<g transform="translate(380,680)"><circle class="node-bg" r="46"/><g class="ico" transform="translate(-19,-15)"><circle cx="13" cy="9" r="6.5"/><path d="M2 32 c0-7.5 5.5-12 11-12 s11 4.5 11 12"/><circle cx="30" cy="12" r="5.5"/><path d="M26 32 c0-6.5 4.5-10 8.5-10 s4.5 1 4.5 1"/></g></g>' +
		'<g transform="translate(120,530)"><circle class="node-bg" r="46"/><g class="ico" transform="translate(-17,-16)"><polyline points="0,8 4,12 11,3"/><line x1="17" y1="8" x2="34" y2="8"/><polyline points="0,25 4,29 11,20"/><line x1="17" y1="25" x2="34" y2="25"/></g></g>' +
		'<g transform="translate(120,230)"><circle class="node-bg" r="46"/><g class="ico" transform="translate(-17,-17)"><circle cx="17" cy="17" r="6.5"/><path d="M17 0 v6.5 M17 27.5 v6.5 M0 17 h6.5 M27.5 17 h6.5 M5 5 l4.5 4.5 M24.5 24.5 l4.5 4.5 M29 5 l-4.5 4.5 M9.5 24.5 l-4.5 4.5"/></g></g>' +
		// central core: original logo (tagline swapped) + glow + new tagline text
		'<defs><radialGradient id="nexglow" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#7fd3e6" stop-opacity=".22"/><stop offset="55%" stop-color="#7fd3e6" stop-opacity=".07"/><stop offset="100%" stop-color="#7fd3e6" stop-opacity="0"/></radialGradient></defs>' +
		'<circle cx="380" cy="380" r="170" fill="url(#nexglow)"/>' +
		'<image href="' + logo + '" x="275" y="252" width="210" height="223"/>' +
		'<text class="tagline" x="380" y="497" text-anchor="middle">BUSINESS APPLICATION SUITE</text>';

	var art = document.createElement("div");
	art.className = "nexum-art";
	art.setAttribute("aria-hidden", "true");
	art.innerHTML = '<svg class="net" viewBox="0 0 760 760" preserveAspectRatio="xMidYMid meet">' + svg + "</svg>";
	document.body.insertBefore(art, document.body.firstChild);
})();

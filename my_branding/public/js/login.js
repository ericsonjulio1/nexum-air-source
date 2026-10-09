/* Nexum Air split sign-in: approved industrial loop + native Frappe form.
 * Media loads only on desktop. Reduced-motion and data-saving preferences
 * use the poster; playback failure never hides it.
 */
(function () {
	var root = document.getElementById("page-login");
	if (!root || document.querySelector(".nexum-art")) return;
	document.body.classList.add("nexum-login");
	document.title = "Sign in · Nexum Air";
	var form = document.querySelector("form.form-login");
	if (form && form.parentNode && !form.parentNode.querySelector(".nexum-login-head")) {
		var head = document.createElement("div");
		head.className = "nexum-login-head";
		head.innerHTML = "<h1>Sign in to Nexum Air</h1><p>Your business application suite.</p>";
		form.parentNode.insertBefore(head, form);
	}

	var asset = "/assets/my_branding/video/nexumair-plant-20261003-v5";
	var art = document.createElement("div");
	art.className = "nexum-art";
	var poster = document.createElement("img");
	poster.className = "nexum-plant-poster";
	poster.alt = "";
	poster.decoding = "async";
	var video = document.createElement("video");
	video.className = "nexum-plant-loop";
	video.setAttribute("aria-hidden", "true");
	video.setAttribute("muted", "");
	video.setAttribute("playsinline", "");
	video.muted = true;
	video.defaultMuted = true;
	video.playsInline = true;
	video.loop = true;
	video.preload = "none";
	var toggle = document.createElement("button");
	toggle.type = "button";
	toggle.className = "nexum-motion-toggle";
	toggle.textContent = "Pause motion";
	toggle.hidden = true;
	art.appendChild(poster);
	art.appendChild(video);
	art.appendChild(toggle);
	document.body.insertBefore(art, document.body.firstChild);

	var desktop = window.matchMedia("(min-width: 881px)");
	var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
	var connection = navigator.connection;
	var posterLoaded = false;
	var sourcesLoaded = false;
	var userPaused = false;
	var failed = false;
	function stillOnly() {
		return reduced.matches || (connection && connection.saveData);
	}
	function shouldPlay() {
		return desktop.matches && !stillOnly() && !document.hidden && !userPaused && !failed;
	}
	function update() {
		if (desktop.matches && !posterLoaded) {
			poster.src = asset + "-poster.jpg";
			video.poster = poster.src;
			posterLoaded = true;
		}
		if (!shouldPlay()) {
			video.pause();
			if (stillOnly() || failed) art.classList.remove("has-video");
			toggle.hidden = !desktop.matches || stillOnly() || !sourcesLoaded || failed;
			toggle.textContent = userPaused ? "Play motion" : "Pause motion";
			return;
		}
		if (!sourcesLoaded) {
			["webm", "mp4"].forEach(function (format) {
				var source = document.createElement("source");
				source.src = asset + "." + format;
				source.type = "video/" + format;
				video.appendChild(source);
			});
			sourcesLoaded = true;
			video.load();
		}
		var play = video.play();
		if (play && play.catch) {
			play.catch(function () {
				if (!shouldPlay()) return;
				art.classList.remove("has-video");
				userPaused = true;
				toggle.textContent = "Play motion";
				toggle.hidden = false;
			});
		}
	}
	video.addEventListener("playing", function () {
		if (!shouldPlay()) { update(); return; }
		art.classList.add("has-video");
		toggle.textContent = "Pause motion";
		toggle.hidden = false;
	});
	video.addEventListener("error", function () {
		failed = true;
		update();
	});
	toggle.addEventListener("click", function () {
		userPaused = !userPaused;
		update();
	});
	[desktop, reduced].forEach(function (query) {
		if (query.addEventListener) query.addEventListener("change", update);
		else query.addListener(update);
	});
	if (connection && connection.addEventListener) connection.addEventListener("change", update);
	document.addEventListener("visibilitychange", update);
	update();
})();

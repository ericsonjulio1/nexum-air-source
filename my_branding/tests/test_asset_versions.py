"""Brand image/font/video URLs must be versioned with ONE token and display-sized (Fable F2, F5).
Stdlib only, no frappe import."""
import ast
import hashlib
import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # my_branding/ package dir
TOKEN = "20261117-perf"
# sha256 of the brand bytes the token was minted for. If you change one of these files, bump
# _ASSET_VER in hooks.py and every other literal (see scripts/REBRAND.md), then update the pin.
PINS = {
	"public/images/nexum-mark-white.png": "eea2e4a2dd6e05bdc2048651c06c5acf79c3b69d68d98dfad2376b0f655b5787",
	"public/images/nexum-mark.png": "d74c8472364a820bb5a067b427169d493e122e31af4ea98c40b9d2ae8bdb3798",
	"public/images/favicon.png": "4df9d61e4931a5e8b6fc6ae622372d4d61dd0efdb06482c70f4a6ecdfc2b4a61",
	"public/fonts/plex-mono-subset.woff2": "727da9951b017fbd7c437be497c4ae01922e1b7693269d84da59e2a2e510ec47",
}
SCAN_SUFFIXES = {".py", ".js", ".css", ".scss", ".html", ".json"}
SKIP_DIRS = {"tests", "node_modules", "dist", "__pycache__"}
LITERAL = re.compile(
	r"/assets/my_branding/(?:images|fonts|video)/[\w./-]+\.(?:png|svg|jpg|jpeg|gif|ico|avif|webp|woff2|webm|mp4)"
	r"(\?v=(?:[\w.-]+|\{_ASSET_VER\}))?")


def scanned_files():
	for p in sorted(ROOT.rglob("*")):
		rel = p.relative_to(ROOT)
		if p.is_file() and p.suffix in SCAN_SUFFIXES and not SKIP_DIRS.intersection(rel.parts[:-1]):
			yield rel


def png_size(path):
	with open(path, "rb") as fh:
		head = fh.read(24)
	return struct.unpack(">II", head[16:24])


def hooks_names(*names):
	"""Evaluate the named hooks.py assignments, with module-level string constants bound."""
	tree = ast.parse((ROOT / "hooks.py").read_text(encoding="utf-8"))
	consts, targets = {}, {}
	for node in tree.body:
		if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
			n = node.targets[0].id
			if n in names:
				targets[n] = node.value
			if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
				consts[n] = node.value.value
	out = {}
	for n in names:
		assert n in targets, n
		out[n] = eval(compile(ast.Expression(targets[n]), "hooks.py", "eval"), {"__builtins__": {}}, consts)
	return out


def ast_assignment(path, name):
	assert Path(path).name == "hooks.py"
	return hooks_names(name)[name]


class AssetVersions(unittest.TestCase):
	def test_every_brand_literal_is_versioned_with_the_one_token(self):
		bare, stale = [], []
		for name in scanned_files():
			text = (ROOT / name).read_text(encoding="utf-8", errors="ignore")
			for m in LITERAL.finditer(text):
				if not m.group(1):
					bare.append(f"{name}:{m.group(0)}")
					continue
				ver = m.group(1)[3:].replace("{_ASSET_VER}", TOKEN)
				if ver != TOKEN and not (m.group(0).split("?")[0].endswith(".svg") and re.fullmatch(r"c\d+", ver)):
					stale.append(f"{name}:{m.group(0)}")
		self.assertEqual(bare, [])
		self.assertEqual(stale, [], "one token everywhere: bump all literals together")

	def test_hooks_values_end_with_the_token(self):
		h = hooks_names("_ASSET_VER", "app_logo_url", "website_context")
		self.assertEqual(h["_ASSET_VER"], TOKEN)
		self.assertTrue(h["app_logo_url"].endswith("?v=" + TOKEN))
		self.assertTrue(h["website_context"]["favicon"].endswith("?v=" + TOKEN))
		self.assertTrue(h["website_context"]["splash_image"].endswith("?v=" + TOKEN))

	def test_the_splash_image_is_the_small_coloured_mark(self):
		ctx = hooks_names("website_context")["website_context"]
		self.assertTrue(ctx["splash_image"].startswith("/assets/my_branding/images/nexum-mark.png?v="))
		self.assertNotIn("nexum-logo-full", (ROOT / "hooks.py").read_text(encoding="utf-8"))

	def test_login_media_urls_carry_the_version_after_the_extension(self):
		src = (ROOT / "public/js/login.js").read_text(encoding="utf-8")
		self.assertIn('var version = "?v=%s";' % TOKEN, src)
		built = [l for l in src.splitlines() if re.search(r"\basset\s*\+", l)]
		self.assertTrue(built)
		self.assertEqual([l for l in built if not re.search(r"\+\s*version\b", l)], [])
		lines = [l for l in src.splitlines() if re.search(r'\.(webm|mp4|jpg|webp)"', l)]
		self.assertTrue(lines)
		self.assertEqual([l for l in lines if "?v=" not in l and "version" not in l], [])

	def test_brand_images_are_display_sized(self):
		for name, max_w in (("nexum-mark-white.png", 450), ("nexum-mark.png", 256), ("favicon.png", 128)):
			p = ROOT / "public/images" / name
			w, _h = png_size(p)
			self.assertLessEqual(w, max_w, name)
			self.assertLessEqual(p.stat().st_size, 40_000, name)

	def test_brand_asset_bytes_match_the_pins(self):
		changed = [rel for rel, want in PINS.items()
			if hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() != want]
		self.assertEqual(changed, [], "brand asset bytes changed: bump _ASSET_VER everywhere and update the pin")


if __name__ == "__main__":
	unittest.main()

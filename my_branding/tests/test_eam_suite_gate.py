"""Release-gate evidence controls; no Frappe, Docker, network or production access.

python3 -m unittest discover -s my_branding/tests -p test_eam_suite_gate.py -v
"""

import ast
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "saas" / "eam_suite_gate.py"
if not HELPER.is_file():
	raise unittest.SkipTest(
		"Server-side EAM gate tests require saas/eam_suite_gate.py; saas/ is omitted from the public source mirror."
	)
SPEC = importlib.util.spec_from_file_location("eam_suite_gate", HELPER)
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
IMAGE = "sha256:" + "a" * 64
OTHER_IMAGE = "sha256:" + "b" * 64


def bench(ran=2236, result="OK (skipped=6)"):
	return f"Ran {ran} tests in 12.345s\n\n{result}\n"


def tap(tests=3, passed=3, failed=0, cancelled=0, skipped=0, todo=0):
	return (
		f"TAP version 13\nok 1 - example suite\n1..1\n# tests {tests}\n# suites 1\n"
		f"# pass {passed}\n# fail {failed}\n# cancelled {cancelled}\n# skipped {skipped}\n"
		f"# todo {todo}\n# duration_ms 15.001\n"
	)


class TestMirrorDistribution(unittest.TestCase):
	def test_app_only_mirror_skips_module_without_import_errors(self):
		with tempfile.TemporaryDirectory() as temporary:
			tests = Path(temporary) / "my_branding" / "tests"
			tests.mkdir(parents=True)
			(tests / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
			result = subprocess.run(
				[
					sys.executable,
					"-m",
					"unittest",
					"discover",
					"-s",
					str(tests),
					"-p",
					Path(__file__).name,
					"-v",
				],
				cwd=temporary,
				capture_output=True,
				text=True,
				timeout=10,
			)
			self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
			self.assertIn("OK (skipped=1)", result.stderr)
			self.assertIn("saas/eam_suite_gate.py", result.stderr)
			self.assertIn("omitted from the public source mirror", result.stderr)


class TestBenchParser(unittest.TestCase):
	def test_full_frappe_categories_are_summed(self):
		text = "Running 435 integration tests for eam\n" + bench(435, "OK (skipped=1)")
		text += "Running 1801 unspecified-category tests for eam\n" + bench(1801, "OK (skipped=5)")
		result = GATE.parse_bench(text, 0)
		self.assertTrue(result["pass"], result)
		self.assertEqual(
			(result["ran"], result["failures"], result["errors"], result["skipped"]), (2236, 0, 0, 6)
		)

	def test_failure_in_first_category_cannot_be_hidden_by_last_ok(self):
		result = GATE.parse_bench(bench(435, "FAILED (errors=2, skipped=1, failures=3)") + bench(1801), 0)
		self.assertFalse(result["pass"])
		self.assertEqual((result["ran"], result["failures"], result["errors"]), (2236, 3, 2))

	def test_nonzero_exit_even_with_ok_is_not_a_pass(self):
		for code in (1, 124, 137, 143, -1):
			with self.subTest(code=code):
				self.assertFalse(GATE.parse_bench(bench(), code)["pass"])

	def test_minimum_count_inclusive_and_overridable(self):
		self.assertTrue(GATE.parse_bench(bench(2000), 0)["pass"])
		self.assertFalse(GATE.parse_bench(bench(1999), 0)["pass"])
		self.assertTrue(GATE.parse_bench(bench(435), 0, 400)["pass"])

	def test_ansi_carriage_returns_single_test_and_counter_order(self):
		text = "\x1b[32mRan 1 test in 0.001s\x1b[0m\r\n\r\n\x1b[32mOK\x1b[0m\r\n"
		self.assertTrue(GATE.parse_bench(text, 0, 1)["pass"])
		self.assertTrue(GATE.parse_bench(bench(result="OK (expected failures=2, skipped=6)"), 0)["pass"])

	def test_missing_truncated_or_duplicate_results_fail_closed(self):
		for text in (
			"",
			"OK\n",
			"Ran 2200 tests in 1.2s\n",
			bench() + "OK\n",
			bench() + "Ran 3 tests in 1s\n",
			"Ran 4 tests in 1s\n" + bench(),
			bench() + "Running 500 integration tests for eam\n",
		):
			with self.subTest(text=text):
				self.assertFalse(GATE.parse_bench(text, 0)["pass"])

	def test_malformed_or_unsuccessful_counters_fail_closed(self):
		for result in (
			"FAILED",
			"FAILED (failures=0)",
			"OK (errors=1)",
			"OK (failures=1)",
			"OK (skipped=-1)",
			"OK (skipped=many)",
			"OK (skipped=1, skipped=2)",
			"OK ()",
			"OK (unknown=1)",
			"OK (unexpected successes=1)",
			"OK (skipped=3000)",
		):
			with self.subTest(result=result):
				self.assertFalse(GATE.parse_bench(bench(result=result), 0)["pass"])

	def test_error_after_success_or_malformed_ran_is_rejected(self):
		for extra in (
			"ERROR: import failed\n",
			"FAIL: hidden failure\n",
			"Traceback (most recent call last):\n",
			"Ran many tests in 1s\n",
		):
			with self.subTest(extra=extra):
				self.assertFalse(GATE.parse_bench(bench() + extra, 0)["pass"])


class TestNodeParser(unittest.TestCase):
	def test_nonempty_complete_tap_passes(self):
		result = GATE.parse_node(tap(), 0)
		self.assertTrue(result["pass"], result)
		self.assertEqual((result["tests"], result["passed"]), (3, 3))

	def test_test_skips_are_counted(self):
		result = GATE.parse_node(tap(passed=2, skipped=1), 0)
		self.assertTrue(result["pass"], result)
		self.assertEqual(result["skipped"], 1)

	def test_failure_cancellation_todo_and_all_skipped_fail(self):
		for text in (
			tap(passed=2, failed=1),
			tap(passed=2, cancelled=1),
			tap(passed=2, todo=1),
			tap(passed=0, skipped=3),
			tap(tests=0, passed=0),
			tap().replace("ok 1", "not ok 1"),
		):
			with self.subTest(text=text):
				self.assertFalse(GATE.parse_node(text, 0)["pass"])

	def test_missing_duplicate_or_inconsistent_footer_fails(self):
		for text in (
			"",
			"ok 1 - test\n",
			tap().replace("# fail 0\n", ""),
			tap() + "# tests 3\n",
			tap().replace("# duration_ms 15.001\n", ""),
			tap().replace("1..1\n", ""),
			tap(tests=4),
			tap().replace("1..1", "1..0"),
		):
			with self.subTest(text=text):
				self.assertFalse(GATE.parse_node(text, 0)["pass"])

	def test_nonzero_exit_fails_even_after_success_footer(self):
		for code in (1, 124, 137, -1):
			with self.subTest(code=code):
				self.assertFalse(GATE.parse_node(tap(), code)["pass"])


class TestHostRefusals(unittest.TestCase):
	def test_reset_window_boundaries_and_next_day(self):
		for instant, budget, expected in (
			("2026-10-21T16:19:59", 90, False),
			("2026-10-21T16:20:00", 90, True),
			("2026-10-21T17:49:59", 1, True),
			("2026-10-21T17:50:00", 1, True),
			("2026-10-21T18:14:59", 1, True),
			("2026-10-21T18:15:00", 1, True),
			("2026-10-21T18:30:00", 1, True),
			("2026-10-21T18:59:59", 1, True),
			("2026-10-21T19:00:00", 90, False),
			("2026-10-21T23:30:00", 90, False),
			("2026-10-21T23:30:00", 1100, True),
			("2026-10-21T01:00:00", 1440, True),
		):
			with self.subTest(instant=instant, budget=budget):
				now = datetime.fromisoformat(instant).replace(tzinfo=GATE.UTC)
				self.assertEqual(GATE.overlaps_reset(now, budget), expected)

	def test_memory_threshold_and_missing_memavailable(self):
		with patch.object(GATE, "overlaps_reset", return_value=False):
			self.assertEqual(GATE.preflight(90, "MemAvailable: 3145728 kB\n"), 3145728)
			for info in (
				"MemAvailable: 2621440 kB\n",
				"MemAvailable: 3145727 kB\n",
				"MemFree: 9999999 kB\n",
				"",
			):
				with self.subTest(info=info), self.assertRaises(ValueError):
					GATE.preflight(90, info)

	def test_new_output_only_outside_worktrees_and_symlinks(self):
		with tempfile.TemporaryDirectory() as temporary:
			root = Path(temporary)
			out = GATE.create_output(root / "evidence")
			self.assertEqual(out.stat().st_mode & 0o777, 0o700)
			with self.assertRaises(FileExistsError):
				GATE.create_output(out)
			repo = root / "mirror"
			repo.mkdir()
			(repo / ".git").touch()  # also catches linked worktrees
			(root / "alias").symlink_to(repo)
			for name in ("mirror", "alias"):
				with self.subTest(name=name), self.assertRaises(ValueError):
					GATE.create_output(root / name / "logs")

	def test_passwords_redacted_before_binary_output(self):
		passwords = [b"root-secret", b"admin-secret", b"site-secret"]
		output = io.BytesIO()
		GATE.redact(
			io.BytesIO(b"root-secret\radmin-secret site-secret\ninvalid utf8: \xff root-secret"),
			output,
			passwords,
		)
		self.assertEqual(
			output.getvalue(), b"[REDACTED]\r[REDACTED] [REDACTED]\ninvalid utf8: \xff [REDACTED]"
		)

	def test_cleanup_prefix_cannot_target_production(self):
		# Exercise the actual shell guard, without executing any Docker commands.
		definition = next(
			line
			for line in (ROOT / "saas/eam-suite-gate.sh").read_text().splitlines()
			if line.startswith("safe_project()")
		)
		for project, expected in (
			("nexum", False),
			("nexum-backend-1", False),
			("nexum-eamtest-", False),
			("nexum-eamtest-20261021t120000z-123", True),
			("nexum-eamtest-20261021t120000z-123; echo unsafe", False),
		):
			with self.subTest(project=project):
				result = subprocess.run(
					["bash", "-c", definition + "\nPROJECT=$1\nsafe_project", "test", project]
				)
				self.assertEqual(result.returncode == 0, expected)

	def test_capture_redacts_both_streams_and_preserves_exit_status(self):
		# Use the real shell capture and Python redactor, with a harmless local command.
		# Only timeout is replaced (not installed on macOS); no Docker command is called.
		source = (ROOT / "saas/eam-suite-gate.sh").read_text()
		capture = source[source.index("capture() {") : source.index("step() {")]
		with tempfile.TemporaryDirectory() as temporary:
			out = Path(temporary)
			env_file, fifo = out / "gate.env", out / "output.pipe"
			generated = subprocess.run(
				[sys.executable, str(ROOT / "saas/eam_suite_gate.py"), "secrets", str(env_file), IMAGE],
				capture_output=True,
				text=True,
			)
			self.assertEqual(generated.returncode, 0, generated.stderr)
			self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)
			os.mkfifo(fifo, 0o600)
			script = (
				"""set -Eeuo pipefail
HELPER=$1; OUT=$2; ENV_FILE=$3; FIFO=$4
timeout() { shift 2; "$@"; }
"""
				+ capture
				+ """
capture 10 command.log bash -c 'source "$1"; printf "out=%s\\n" "$EAM_GATE_DB_PASSWORD"; printf "err=%s\\n" "$EAM_GATE_ADMIN_PASSWORD" >&2; exit 7' fixture "$ENV_FILE"
"""
			)
			result = subprocess.run(
				[
					"bash",
					"-c",
					script,
					"capture-test",
					str(ROOT / "saas/eam_suite_gate.py"),
					str(out),
					str(env_file),
					str(fifo),
				],
				capture_output=True,
				text=True,
				timeout=10,
			)
			self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
			self.assertEqual((out / "command.log").read_text(), "out=[REDACTED]\nerr=[REDACTED]\n")
			self.assertEqual(result.stdout, "")
			self.assertEqual(result.stderr, "")


class TestHostFixes(unittest.TestCase):
	"""Pin the resource limits, fresh-site bootstrap and teardown validated on the host."""

	@classmethod
	def setUpClass(cls):
		cls.script = (ROOT / "saas/eam-suite-gate.sh").read_text()

	def python_step(self, log):
		matches = list(
			re.finditer(
				rf"^step {re.escape(log)} ([^\n]+) -c '\n(.*?)^'[^\n]*$",
				self.script,
				re.MULTILINE | re.DOTALL,
			)
		)
		self.assertEqual(len(matches), 1, f"expected one in-container Python step for {log}")
		return matches[0]

	def test_all_gate_services_yield_cpu_and_database_has_one_cpu(self):
		compose = (ROOT / "saas/eam-suite-compose.yaml").read_text()
		services_section = compose.split("\nservices:\n", 1)[1].split("\nnetworks:\n", 1)[0]
		# Inspect top-level service fields without adding a YAML dependency to the tests.
		services = dict(
			re.findall(r"^  ([\w-]+):\n(.*?)(?=^  [\w-]+:|\Z)", services_section, re.MULTILINE | re.DOTALL)
		)
		self.assertEqual(set(services), {"app", "db", "redis-cache", "redis-queue"})
		for name, body in services.items():
			with self.subTest(service=name):
				self.assertRegex(body, r"(?m)^    cpu_shares: 256\s*(?:#.*)?$")
		self.assertRegex(services["db"], r"(?m)^    cpus: 1(?:\.0)?\s*(?:#.*)?$")

	def test_python_checks_use_sites_working_directory_and_relative_site_path(self):
		for log in ("installed-apps.log", "before-tests.log"):
			with self.subTest(step=log):
				step = self.python_step(log)
				self.assertEqual(
					shlex.split(step[1]),
					[
						"${C[@]}",
						"exec",
						"-T",
						"-w",
						"/home/frappe/frappe-bench/sites",
						"app",
						"../env/bin/python",
					],
				)
				calls = [
					node
					for node in ast.walk(ast.parse(step[2]))
					if isinstance(node, ast.Call) and ast.unparse(node.func) == "frappe.init"
				]
				self.assertEqual(len(calls), 1)
				kwargs = {item.arg: ast.literal_eval(item.value) for item in calls[0].keywords}
				self.assertEqual(kwargs["site"], "eamtest.localhost")
				self.assertEqual(kwargs["sites_path"], ".")

	def test_hrms_bootstrap_sets_both_test_flags_and_commits_before_suite(self):
		step = self.python_step("before-tests.log")
		self.assertLess(step.start(), self.script.index("step bench.log "))
		events = []
		frappe = ModuleType("frappe")
		frappe.init, frappe.connect = Mock(), Mock()
		frappe.in_test, frappe.flags = False, SimpleNamespace(in_test=False)
		frappe.db = SimpleNamespace(commit=Mock(side_effect=lambda: events.append("commit")))
		frappe.destroy = Mock(side_effect=lambda: events.append("destroy"))
		frappe.get_all = Mock(return_value=["_Test Company"])

		def seed_fixtures():
			self.assertIs(frappe.in_test, True, "Frappe 16 password policy requires frappe.in_test")
			self.assertIs(frappe.flags.in_test, True)
			events.append("before_tests")

		test_utils = ModuleType("hrms.tests.test_utils")
		test_utils.before_tests = Mock(side_effect=seed_fixtures)
		modules = {
			"frappe": frappe,
			"hrms": ModuleType("hrms"),
			"hrms.tests": ModuleType("hrms.tests"),
			"hrms.tests.test_utils": test_utils,
		}
		# Run only the embedded Python against stubs; never import Frappe or execute Compose.
		with patch.dict(sys.modules, modules), redirect_stdout(io.StringIO()):
			exec(compile(step[2], "eam-suite-gate.sh:before-tests", "exec"), {})
		frappe.init.assert_called_once_with(site="eamtest.localhost", sites_path=".")
		frappe.connect.assert_called_once_with()
		test_utils.before_tests.assert_called_once_with()
		self.assertEqual(events, ["before_tests", "commit", "destroy"])

	def test_hrms_is_required_before_bootstrap(self):
		guard = next(
			line
			for line in self.script.splitlines()
			if line.startswith("[[") and "--apps must include hrms" in line
		)
		self.assertLess(self.script.index(guard), self.python_step("before-tests.log").start())
		for apps, expected in (
			("frappe,erpnext,hrms,eam", 0),
			("frappe,erpnext,eam", 1),
			("frappe,erpnext,custom_hrms,eam", 1),
			("frappe,erpnext,hrms_custom,eam", 1),
		):
			with self.subTest(apps=apps):
				result = subprocess.run(
					[
						"bash",
						"-c",
						'refuse() { echo "$*" >&2; exit 1; }\nAPPS=$1\n' + guard,
						"guard-test",
						apps,
					],
					capture_output=True,
					text=True,
					timeout=10,
				)
				self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
				if expected:
					self.assertIn("--apps must include hrms", result.stderr)

	def test_teardown_allows_database_shutdown_and_reserves_150_seconds(self):
		cleanup = self.script[self.script.index("cleanup() {") : self.script.index("\ntrap cleanup EXIT")]
		down = next(
			line
			for line in cleanup.splitlines()
			if line.strip().startswith("capture ") and " cleanup.log " in line
		)
		self.assertEqual(
			shlex.split(down.split("||", 1)[0]),
			["capture", "120", "cleanup.log", "${C[@]}", "down", "-v", "--remove-orphans", "--timeout", "30"],
		)
		reserve = next(line for line in self.script.splitlines() if line.startswith("WORK_SECONDS="))
		for minutes in (30, 90):
			with self.subTest(max_minutes=minutes):
				result = subprocess.run(
					[
						"bash",
						"-c",
						"MAX_MINUTES=$1\n" + reserve + '\nprintf "%s" "$WORK_SECONDS"',
						"reserve-test",
						str(minutes),
					],
					capture_output=True,
					text=True,
					timeout=10,
				)
				self.assertEqual(result.returncode, 0, result.stderr)
				self.assertEqual(int(result.stdout), minutes * 60 - 150)


class TestEvidence(unittest.TestCase):
	def setUp(self):
		self.temporary = tempfile.TemporaryDirectory()
		self.addCleanup(self.temporary.cleanup)
		self.out = Path(self.temporary.name)
		self.initial = {
			"image_id": IMAGE,
			"image_ref": "example/candidate:fixture",
			"min_tests": 2000,
			"started_utc": datetime.now(GATE.UTC).isoformat(),
			"max_minutes": 90,
			"pass": False,
		}
		GATE.write_json(self.out / GATE.STATUS, self.initial)
		(self.out / "bench.log").write_text(bench())
		(self.out / "node-suites.log").write_text("eam/tests/one.test.cjs\neam/tests/two.test.cjs\n")
		(self.out / "node-exits.log").write_text("0\n0\n")
		(self.out / "node-1.log").write_text(tap())
		(self.out / "node-2.log").write_text(tap())
		(self.out / "cleanup.log").write_text("removed\n")

	def finish(self, **changes):
		return GATE.finish(
			self.out,
			**{"bench_exit": 0, "actual_image_id": IMAGE, "run_exit": 0, "cleanup_ok": True, **changes},
		)

	def test_success_includes_all_log_hashes_and_atomic_private_status(self):
		status = self.finish()
		self.assertTrue(status["pass"], status)
		self.assertEqual(len(status["node_results"]), 2)
		for path in self.out.glob("*.log"):
			self.assertEqual(status["log_sha256"][path.name], hashlib.sha256(path.read_bytes()).hexdigest())
		self.assertTrue(status["finished_utc"].endswith("Z"))
		self.assertGreaterEqual(status["duration_seconds"], 0)
		self.assertEqual((self.out / GATE.STATUS).stat().st_mode & 0o777, 0o600)
		self.assertFalse((self.out / "eam-suite-status.tmp").exists())

	def test_setup_signal_cleanup_or_image_mismatch_blocks_success(self):
		for change in (
			{"bench_exit": -1},
			{"run_exit": 1},
			{"run_exit": 143},
			{"cleanup_ok": False},
			{"actual_image_id": OTHER_IMAGE},
		):
			with self.subTest(change=change):
				self.assertFalse(self.finish(**change)["pass"])

	def test_missing_suite_result_or_inventory_cannot_pass(self):
		for filename, content in (
			("node-exits.log", "0\n"),
			("node-exits.log", "0\n0\n0\n"),
			("node-2.log", ""),
			("node-suites.log", ""),
			("node-suites.log", "eam/tests/one.test.cjs\neam/tests/one.test.cjs\n"),
			("node-suites.log", "../../untrusted.test.cjs\neam/tests/two.test.cjs\n"),
		):
			with self.subTest(filename=filename, content=content):
				path = self.out / filename
				original = path.read_text()
				path.write_text(content)
				self.assertFalse(self.finish()["pass"])
				path.write_text(original)

	def test_one_node_failure_blocks_success(self):
		(self.out / "node-exits.log").write_text("0\n1\n")
		self.assertFalse(self.finish()["pass"])

	def test_exhausted_total_budget_blocks_success(self):
		self.initial["started_utc"] = (datetime.now(GATE.UTC) - timedelta(minutes=91)).isoformat()
		GATE.write_json(self.out / GATE.STATUS, self.initial)
		result = self.finish()
		self.assertFalse(result["budget_ok"])
		self.assertFalse(result["pass"])

	def test_verify_requires_boolean_true_and_exact_image_id(self):
		for status in (
			{},
			[],
			{"pass": 1, "image_id": IMAGE},
			{"pass": "true", "image_id": IMAGE},
			{"pass": False, "image_id": IMAGE},
			{"pass": True, "image_id": OTHER_IMAGE},
		):
			with self.subTest(status=status):
				GATE.write_json(self.out / GATE.STATUS, status)
				with self.assertRaises(ValueError):
					GATE.verify(self.out, IMAGE)
		GATE.write_json(self.out / GATE.STATUS, {"pass": True, "image_id": IMAGE})
		GATE.verify(self.out, IMAGE)
		with self.assertRaises(ValueError):
			GATE.verify(self.out, "example/candidate:fixture")

	def test_verify_missing_and_malformed_status(self):
		(self.out / GATE.STATUS).unlink()
		with self.assertRaises(FileNotFoundError):
			GATE.verify(self.out, IMAGE)
		(self.out / GATE.STATUS).write_text("{")
		with self.assertRaises(json.JSONDecodeError):
			GATE.verify(self.out, IMAGE)

	def test_verify_shell_entrypoint_uses_no_docker(self):
		self.finish()
		for expected, code in ((IMAGE, 0), (OTHER_IMAGE, 1)):
			with self.subTest(expected=expected):
				result = subprocess.run(
					["bash", str(ROOT / "saas/eam-suite-gate.sh"), "verify", str(self.out), expected],
					capture_output=True,
					text=True,
				)
				self.assertEqual(result.returncode, code, result.stdout + result.stderr)


if __name__ == "__main__":
	unittest.main()

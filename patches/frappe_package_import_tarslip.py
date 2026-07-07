#!/usr/bin/env python3
"""Stage fix: frappe Package Import TarSlip RCE (GHSA-58w2-4cjg-hvp6 / CVE-2026-55852, HIGH).

Symptom / risk:
    Package Import (Setup > Package Import; System Manager only, which every
    NexumAir tenant owner holds on their OWN site) extracted an uploaded
    <name>-x.y.z.tar.gz by shelling out to `tar xzf ... -C <packages>` with NO
    path validation. A crafted tar containing ../ traversal members or symlinks
    could write files outside the packages dir -> arbitrary file write -> RCE in
    the shared multi-tenant bench container. Affected frappe < 16.23.0; our pin
    is 16.22.0.

Fix (exact upstream patch, frappe >= 16.23.0):
    Replace the subprocess shell-out with tarfile extraction that (a) rejects
    symlink/hardlink members, (b) runs check_path_safety() per member (this
    helper already exists in our 16.22.0 frappe/core/doctype/file/utils.py),
    (c) sanitizes the package name, and (d) uses extractall(filter="data").
    Our pinned file differs from the upstream-fixed file ONLY by this security
    diff (verified byte-for-byte 2026-07-07), so this replaces the whole file.

Usage (run inside the image build, against the baked frappe app):
    python3 frappe_package_import_tarslip.py \
      apps/frappe/frappe/core/doctype/package_import/package_import.py

Idempotent (re-run = no-op), drift-guarded (SystemExit if the file shape moved),
and verifies the result compiles. First shipped to prod as v16-prod-106 (2026-07-07).
"""
import sys, py_compile

PATCHED = r'''# Copyright (c) 2021, Frappe Technologies and contributors
# For license information, please see license.txt

import json
import os
import re
import tarfile

import frappe
from frappe.core.doctype.file.utils import check_path_safety
from frappe.desk.form.load import get_attachments
from frappe.model.document import Document
from frappe.model.sync import get_doc_files
from frappe.modules.import_file import import_doc, import_file_by_path
from frappe.utils import get_files_path


class PackageImport(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		activate: DF.Check
		attach_package: DF.Attach | None
		force: DF.Check
		log: DF.Code | None
	# end: auto-generated types

	def validate(self):
		if self.activate:
			self.import_package()

	def import_package(self):
		attachment = get_attachments(self.doctype, self.name)

		if not attachment:
			frappe.throw(frappe._("Please attach the package"))

		attachment = attachment[0]

		# get package_name from file (package_name-0.0.0.tar.gz)
		raw_name = attachment.file_name.split(".", 1)[0].rsplit("-", 1)[0]
		package_name = re.sub(r"[^a-zA-Z0-9_-]", "", raw_name)
		if not package_name:
			frappe.throw(frappe._("Invalid Package Name"))

		if not os.path.exists(frappe.get_site_path("packages")):
			os.makedirs(frappe.get_site_path("packages"))

		# extract
		extract_path = frappe.get_site_path("packages")
		archive_path = get_files_path(attachment.file_name, is_private=attachment.is_private)
		with tarfile.open(archive_path, "r:gz") as tar:
			for member in tar.getmembers():
				if member.issym() or member.islnk():
					frappe.throw(frappe._(f"Package contains disallowed link entry: {member.name}"))

				member_path = os.path.join(extract_path, member.name)
				is_safe = check_path_safety(extract_path, member_path)
				if not is_safe:
					frappe.throw(frappe._("Package contains disallowed path entry"))

			tar.extractall(path=extract_path, filter="data")

		package_path = frappe.get_site_path("packages", package_name)

		# import Package
		with open(os.path.join(package_path, package_name + ".json")) as packagefile:
			doc_dict = json.loads(packagefile.read())

		frappe.flags.package = import_doc(doc_dict)

		# collect modules
		files = []
		log = []
		for module in os.listdir(package_path):
			module_path = os.path.join(package_path, module)
			if os.path.isdir(module_path):
				files = get_doc_files(files, module_path)

		# import files
		for file in files:
			import_file_by_path(file, force=self.force, ignore_version=True)
			log.append(f"Imported {file}")

		self.log = "\n".join(log)
'''

def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: frappe_package_import_tarslip.py <path/to/package_import.py>")
    target = sys.argv[1]
    src = open(target).read()
    if "check_path_safety" in src and "subprocess.check_output" not in src:
        print("no patch needed (TarSlip already fixed upstream)"); return
    if "subprocess.check_output" in src and '"tar",' in src and '"xzf",' in src:
        open(target, "w").write(PATCHED)
        py_compile.compile(target, doraise=True)
        after = open(target).read()
        assert "check_path_safety" in after and "subprocess.check_output" not in after, "TarSlip patch did not land"
        print("TarSlip patch applied (package_import.py -> vetted tarfile extraction)"); return
    raise SystemExit("package_import.py changed upstream - REVIEW THIS TarSlip PATCH")

if __name__ == "__main__":
    main()

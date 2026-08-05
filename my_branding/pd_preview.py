"""Heal print_designer's default-format preview images.

Upstream print_designer ships preview jpgs inside the app (default_templates/)
and its default-format JSONs reference them via print_designer_preview_img, but
the code that copies the jpg into the site is commented out upstream (pending
frappe/frappe#25779). Result: every install creates a dangling attach value,
frappe core's attach_files_to_document then fails FileNotFoundError on_update —
two "Error Attaching File" logs on every fresh tenant.

This reconciler completes upstream's intended copy: physical jpg -> site private
files + a File doc attached to the Print Format, then deletes the now-stale
"Error Attaching File" logs for the healed files. Idempotent; no-op without
print_designer.
"""

import os

import frappe


def ensure_pd_preview_images():
    if "print_designer" not in frappe.get_installed_apps():
        return

    try:
        from print_designer.default_formats import get_preview_image_folder_path
    except ImportError:
        return

    formats = frappe.get_all(
        "Print Format",
        filters={"print_designer": 1},
        fields=["name", "print_designer_preview_img", "print_designer_template_app"],
    )
    for pf in formats:
        if not pf.print_designer_preview_img:
            continue
        try:
            _heal_preview(pf)
        except Exception:
            frappe.log_error(
                title="ensure_pd_preview_images failed",
                message=f"{pf.name}: {frappe.get_traceback()}",
            )


def _heal_preview(pf):
    file_name = pf.print_designer_preview_img.split("/")[-1]
    attached = frappe.db.exists(
        "File",
        {
            "attached_to_doctype": "Print Format",
            "attached_to_name": pf.name,
            "attached_to_field": "print_designer_preview_img",
        },
    )
    if attached:
        return

    from print_designer.default_formats import get_preview_image_folder_path

    doc = frappe.get_doc("Print Format", pf.name)
    src = os.path.join(get_preview_image_folder_path(doc), file_name)
    if not os.path.exists(src):
        # jpg genuinely absent from the app: the reference is unhealable — clear
        # it so attach_files_to_document stops erroring on every future save
        frappe.db.set_value(
            "Print Format", pf.name, "print_designer_preview_img", None, update_modified=False
        )
        return

    with open(src, "rb") as f:
        content = f.read()

    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "is_private": 1,
            "attached_to_doctype": "Print Format",
            "attached_to_name": pf.name,
            "attached_to_field": "print_designer_preview_img",
            "content": content,
        }
    ).insert(ignore_permissions=True)

    # frappe's attach check keys on EXACT file_url == field value; File.insert
    # may dedup-rename, so point the field at wherever the file actually landed
    # (upstream's commented-out fix does the same)
    if file_doc.file_url != pf.print_designer_preview_img:
        frappe.db.set_value(
            "Print Format",
            pf.name,
            "print_designer_preview_img",
            file_doc.file_url,
            update_modified=False,
        )

    # the failed-attach logs for this file are now stale debris
    frappe.db.sql(
        """delete from `tabError Log`
           where method = 'Error Attaching File' and error like %(pat)s""",
        {"pat": f"%{file_name}%"},
    )

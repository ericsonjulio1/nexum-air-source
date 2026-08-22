"""Heal the seeded "Philippines 2026" Holiday List to match Proclamation No. 1006.

The original seed marked Feb 25 (EDSA) as a holiday — it is a special WORKING day
in 2026 — and omitted Chinese New Year (Feb 17), Black Saturday (Apr 4), All
Souls' Day (Nov 2) and Christmas Eve (Dec 24), all declared special non-working
days. Rewrites the child rows ONLY when the list still contains exactly what the
old generator produced; any tenant edit (added, removed or renamed rows) means
the list is theirs and it is left alone.
"""

import frappe

# byte-for-byte what the OLD _ph_holidays(2026) generator seeded
_OLD_2026 = {
    ("2026-01-01", "New Year's Day"),
    ("2026-02-25", "EDSA People Power Anniversary"),
    ("2026-04-02", "Maundy Thursday"),
    ("2026-04-03", "Good Friday"),
    ("2026-04-09", "Araw ng Kagitingan (Day of Valor)"),
    ("2026-05-01", "Labor Day"),
    ("2026-06-12", "Independence Day"),
    ("2026-08-21", "Ninoy Aquino Day"),
    ("2026-08-31", "National Heroes Day"),
    ("2026-11-01", "All Saints' Day"),
    ("2026-11-30", "Bonifacio Day"),
    ("2026-12-08", "Immaculate Conception"),
    ("2026-12-25", "Christmas Day"),
    ("2026-12-30", "Rizal Day"),
    ("2026-12-31", "Last Day of the Year"),
}


def execute():
    if not frappe.db.table_exists("Holiday List"):
        return
    name = "Philippines 2026"
    if not frappe.db.exists("Holiday List", name):
        return
    doc = frappe.get_doc("Holiday List", name)
    current = {(str(h.holiday_date), (h.description or "").strip()) for h in doc.holidays}
    if current != _OLD_2026:
        return  # tenant-edited — hands off

    from my_branding.setup_apps import _ph_holidays

    doc.set("holidays", [])
    for date, desc in _ph_holidays(2026):
        doc.append("holidays", {"holiday_date": date, "description": desc})
    doc.flags.ignore_permissions = True
    doc.save()

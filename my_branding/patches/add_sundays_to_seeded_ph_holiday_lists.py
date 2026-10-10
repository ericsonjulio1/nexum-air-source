"""Add the Sunday weekly-off rows the seeded "Philippines <year>" Holiday Lists never got
(batch205 idx 160).

setup_apps.run() created the list with weekly_off = "Sunday" but only the named holidays:
the weekly_off field merely feeds the list's "Add to Holidays" button, so HR counted every
Sunday as a working day (leave days, payroll working days, auto-attendance absences).
run() now adds them to new lists; this patch fixes the lists already seeded.

Only a list nobody has worked on is touched. "Unedited" means ALL of:
  * named exactly "Philippines <year>", as run() names it;
  * the header run() wrote: weekly_off "Sunday", 1 Jan - 31 Dec of that year, no half
    day, no colour, no country/subdivision (the "local holidays" helper sets those);
  * its rows are exactly what the generator yields for that year (_ph_holidays: for 2026
    the Proclamation 1006 set heal_ph_holiday_list_2026 rewrites the old seed to, which is
    why this patch runs after it): same dates, same names, none added, removed or made
    half-day, and no weekly-off row at all, i.e. "Add to Holidays" was never used;
  * last saved by Administrator: run() (bench execute) and the heal patch both run as
    Administrator, so a save by any tenant user leaves the list alone — even one that put
    the rows back exactly as seeded, such as taking Sundays out again on purpose.
Anything else is the tenant's own calendar and is left exactly as it is.

Leave Applications, Salary Slips and attendance already computed from these lists are not
recomputed.
"""

import datetime
import re

import frappe
from frappe.utils import getdate

_NAME = re.compile(r"^Philippines (\d{4})$")


def _unedited_seed(doc, year):
    from my_branding.setup_apps import _ph_holidays

    if doc.holiday_list_name != doc.name or doc.weekly_off != "Sunday":
        return False
    if getdate(doc.from_date) != datetime.date(year, 1, 1) or getdate(doc.to_date) != datetime.date(year, 12, 31):
        return False
    if doc.get("is_half_day") or doc.get("color") or doc.get("country") or doc.get("subdivision"):
        return False
    if doc.modified_by != "Administrator":
        return False
    rows = doc.get("holidays") or []
    if any(r.weekly_off or r.is_half_day for r in rows):
        return False
    seeded = _ph_holidays(year)
    current = [(str(getdate(r.holiday_date)), (r.description or "").strip()) for r in rows]
    return len(current) == len(seeded) and set(current) == set(seeded)


def execute():
    if not frappe.db.table_exists("Holiday List"):
        return
    for name in frappe.get_all("Holiday List", filters={"name": ["like", "Philippines %"]}, pluck="name"):
        match = _NAME.match(name)
        if not match:
            continue
        doc = frappe.get_doc("Holiday List", name)
        if not _unedited_seed(doc, int(match.group(1))):
            continue  # the tenant's calendar now — hands off
        doc.get_weekly_off_dates()
        doc.flags.ignore_permissions = True
        doc.save()

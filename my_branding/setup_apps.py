"""Per-tenant baseline setup for the bundled apps. Run via:
    bench --site <site> execute my_branding.setup_apps.run
    bench --site <site> execute my_branding.setup_apps.run --kwargs '{"admin_user": "owner@acme.com"}'

Idempotent + TENANT-AGNOSTIC: detects THIS site's own admin user + company at
runtime (no hardcoded account), so it's safe on hq AND on any customer tenant.
Each app's step is guarded so it cleanly skips when that app isn't installed.
"""
import json
import frappe


def _easter(year):
    """Gregorian Easter Sunday for `year` (Anonymous Gregorian / computus algorithm).
    Used to derive Maundy Thursday + Good Friday, the only movable PH holidays here."""
    import datetime

    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


def _ph_holidays(year):
    """Philippine regular + special non-working holidays with FIXED or computable
    dates for `year`, as sorted (YYYY-MM-DD, description) tuples. Excludes the lunar
    Islamic holidays (Eid'l Fitr / Eid'l Adha), whose Gregorian dates are proclaimed
    yearly and can't be derived. Replaces the old hardcoded 2026-only list so a tenant
    provisioned in any year gets that year's calendar."""
    import datetime

    easter = _easter(year)
    # National Heroes Day = last Monday of August
    nhd = datetime.date(year, 8, 31)
    while nhd.weekday() != 0:  # 0 = Monday
        nhd -= datetime.timedelta(days=1)
    items = [
        (datetime.date(year, 1, 1), "New Year's Day"),
        (datetime.date(year, 2, 25), "EDSA People Power Anniversary"),
        (easter - datetime.timedelta(days=3), "Maundy Thursday"),
        (easter - datetime.timedelta(days=2), "Good Friday"),
        (datetime.date(year, 4, 9), "Araw ng Kagitingan (Day of Valor)"),
        (datetime.date(year, 5, 1), "Labor Day"),
        (datetime.date(year, 6, 12), "Independence Day"),
        (datetime.date(year, 8, 21), "Ninoy Aquino Day"),
        (nhd, "National Heroes Day"),
        (datetime.date(year, 11, 1), "All Saints' Day"),
        (datetime.date(year, 11, 30), "Bonifacio Day"),
        (datetime.date(year, 12, 8), "Immaculate Conception"),
        (datetime.date(year, 12, 25), "Christmas Day"),
        (datetime.date(year, 12, 30), "Rizal Day"),
        (datetime.date(year, 12, 31), "Last Day of the Year"),
    ]
    items.sort(key=lambda t: t[0])
    return [(d.strftime("%Y-%m-%d"), desc) for d, desc in items]


def _site_admin(explicit=None):
    """The site's own admin: the explicit email if it exists here, else the first
    enabled System Manager that isn't Administrator/Guest. None if none found."""
    if explicit and frappe.db.exists("User", explicit):
        return explicit
    for u in frappe.get_all(
        "Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent"
    ):
        if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled"):
            return u
    return None


def _site_company():
    """This site's default company, else the first Company. None if none yet."""
    return frappe.defaults.get_global_default("company") or (
        (frappe.get_all("Company", limit=1, pluck="name") or [None])[0]
    )


def grant_insights(user=None):
    """Grant Insights roles so the Insights SPA loads (get_user_info 403 otherwise)."""
    user = _site_admin(user)
    if not user:
        print("RESULT=" + repr({"error": "no admin user found on this site"}))
        return
    roles = [r for r in frappe.get_all("Role", filters={"name": ["like", "Insights%"]}, pluck="name")]
    doc = frappe.get_doc("User", user)
    doc.add_roles(*roles)
    frappe.db.commit()
    print("RESULT=" + repr({"insights_roles_available": roles, "granted_to": user,
                            "user_now_has": [r for r in frappe.get_roles(user) if "Insights" in r]}))


def apps_list():
    """Authoritative app-switcher data (name/title/logo) used by /apps and navbar."""
    import json as _j
    try:
        from frappe.apps import get_apps
        data = get_apps()
        out = [{"name": a.get("name"), "title": a.get("title"), "logo": a.get("logo"), "route": a.get("route")} for a in data]
    except Exception as e:
        out = "ERR: " + str(e)
    print("APPSLIST=" + _j.dumps(out, default=str))


def app_logos():
    """Print the app_logo_url each installed app registers (the /apps switcher icon src)."""
    import json as _j
    apps = ["hrms", "helpdesk", "crm", "gameplan", "builder", "lms", "insights",
            "drive", "print_designer", "telephony", "payments", "erpnext", "frappe"]
    out = {}
    for a in apps:
        try:
            h = frappe.get_hooks("app_logo_url", app_name=a)
            out[a] = h[-1] if h else None
        except Exception as e:
            out[a] = "ERR: " + str(e)
    print("LOGOS=" + _j.dumps(out, default=str))


def run(admin_user=None):
    res = {}
    admin = _site_admin(admin_user)
    res["admin_user"] = admin or "(none found)"

    # 1. Insights: data source -> this site's DB (no creds via is_site_db)
    try:
        if not frappe.db.exists("DocType", "Insights Data Source"):
            res["insights_data_source"] = "skip (insights not installed)"
        else:
            existing = frappe.get_all("Insights Data Source", filters={"is_site_db": 1}, pluck="name")
            if existing:
                res["insights_data_source"] = "exists: " + existing[0]
            elif frappe.db.exists("Insights Data Source", "Nexum Air (Site DB)"):
                res["insights_data_source"] = "exists: Nexum Air (Site DB)"
            else:
                ds = frappe.get_doc({
                    "doctype": "Insights Data Source", "title": "Nexum Air (Site DB)",
                    "database_type": "MariaDB", "is_site_db": 1, "status": "Active",
                })
                ds.insert(ignore_permissions=True)
                res["insights_data_source"] = "created: " + ds.name
    except Exception as e:
        res["insights_data_source"] = "ERROR: " + str(e)

    # 1b. Insights: grant the admin the Insights roles. System Manager alone 403s on
    # get_user_info, so without this the Insights SPA won't load for business/
    # enterprise tenants. Idempotent (add_roles skips roles already held).
    try:
        if not frappe.db.exists("DocType", "Insights Data Source"):
            res["insights_roles"] = "skip (insights not installed)"
        elif not admin:
            res["insights_roles"] = "skip (no admin user)"
        else:
            roles = frappe.get_all("Role", filters={"name": ["like", "Insights%"]}, pluck="name")
            if roles:
                frappe.get_doc("User", admin).add_roles(*roles)
                res["insights_roles"] = "granted %d to %s" % (len(roles), admin)
            else:
                res["insights_roles"] = "no Insights roles found"
    except Exception as e:
        res["insights_roles"] = "ERROR: " + str(e)

    # 2. Helpdesk: make THIS site's own admin an active agent (only if Helpdesk installed)
    try:
        if not frappe.db.exists("DocType", "HD Agent"):
            res["helpdesk_agent"] = "skip (helpdesk not installed)"
        elif not admin:
            res["helpdesk_agent"] = "skip (no admin user)"
        elif frappe.db.exists("HD Agent", {"user": admin}):
            res["helpdesk_agent"] = "exists"
        else:
            agent_name = frappe.db.get_value("User", admin, "full_name") or admin
            frappe.get_doc({"doctype": "HD Agent", "user": admin,
                            "agent_name": agent_name, "is_active": 1}).insert(ignore_permissions=True)
            res["helpdesk_agent"] = "created for " + admin
    except Exception as e:
        res["helpdesk_agent"] = "ERROR: " + str(e)

    # 3. HRMS: 2026 Philippines Holiday List + set as HR/company default (only if HR installed)
    try:
        if not frappe.db.exists("DocType", "Holiday List"):
            res["holiday_list"] = "skip (HR not installed)"
        else:
            year = frappe.utils.now_datetime().year
            hl = "Philippines %d" % year
            if not frappe.db.exists("Holiday List", hl):
                hol = _ph_holidays(year)
                doc = frappe.get_doc({"doctype": "Holiday List", "holiday_list_name": hl,
                                      "from_date": "%d-01-01" % year, "to_date": "%d-12-31" % year,
                                      "weekly_off": "Sunday"})
                for d, desc in hol:
                    doc.append("holidays", {"holiday_date": d, "description": desc})
                doc.insert(ignore_permissions=True)
                res["holiday_list"] = "created: %s (%d holidays)" % (doc.name, len(hol))
            else:
                res["holiday_list"] = "exists"
            # run() is advertised as idempotent/safe to re-run, so it must NOT clobber a
            # tenant's own holiday calendar. Only (re)assign the default when the slot is
            # empty or still holds a "Philippines <year>" list this script itself created.
            def _owned(v):
                return not v or (v.startswith("Philippines ") and v[12:].isdigit())
            if frappe.db.exists("DocType", "HR Settings"):
                cur = frappe.db.get_single_value("HR Settings", "default_holiday_list")
                if _owned(cur):
                    frappe.db.set_single_value("HR Settings", "default_holiday_list", hl)
            company = _site_company()
            if company:
                try:
                    cur_c = frappe.db.get_value("Company", company, "default_holiday_list")
                    if _owned(cur_c):
                        frappe.db.set_value("Company", company, "default_holiday_list", hl)
                        res["holiday_default"] = "set on HR Settings + Company '%s'" % company
                    else:
                        res["holiday_default"] = "kept tenant's custom Company default '%s'" % cur_c
                except Exception as e2:
                    res["holiday_default"] = "HR Settings set; company: " + str(e2)
            else:
                res["holiday_default"] = "HR Settings set; no company yet"
    except Exception as e:
        res["holiday_list"] = "ERROR: " + str(e)

    # 4. Gameplan: ensure at least one team exists so it's usable
    try:
        if frappe.db.exists("DocType", "GP Team"):
            teams = frappe.get_all("GP Team", pluck="name")
            if teams:
                res["gameplan_team"] = "exists: %d" % len(teams)
            else:
                # explicit icon: if left unset Gameplan assigns a RANDOM emoji
                # (one tenant drew ✝️ — read as a coffin on the team tile)
                frappe.get_doc(
                    {"doctype": "GP Team", "title": "General", "icon": "💬"}
                ).insert(ignore_permissions=True)
                res["gameplan_team"] = "created: General"
        else:
            res["gameplan_team"] = "skip (no GP Team doctype)"
    except Exception as e:
        res["gameplan_team"] = "ERROR: " + str(e)

    frappe.db.commit()
    print("RESULT=" + json.dumps(res, default=str))
    return res

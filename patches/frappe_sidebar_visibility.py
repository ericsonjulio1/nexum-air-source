#!/usr/bin/env python3
"""Stage fix: frappe v16 sidebars hide ALL doctype/page links from non-Administrator users.

Symptom:
    For any user except literal Administrator, every plain DocType link (and every
    non-domain Page link) disappears from every Workspace Sidebar — native ERPNext
    sidebars included (e.g. a Maintenance User on the Assets sidebar sees only
    "Home" + "Dashboard"). Reports are unaffected; workspace-page CARD links are
    unaffected. Found 2026-08-25 verifying the eam Maintenance workspace on sbl.

Root cause — TWO stacked upstream bugs (both still present on frappe develop as of
2026-08-25), each alone sufficient to hide the links; is_item_allowed
(frappe/desk/desk_views.py) requires BOTH `name in self.can_read` AND
`name in self.restricted_doctypes`:

1. cache_manager.py `build_domain_restricted_doctype_cache` /
   `build_domain_restricted_page_cache` fill the caches with entities whose
   restrict_to_domain is IN the ACTIVE domains only — an entity with NO domain
   tag (NULL, i.e. almost every doctype) is never in the cache, so the
   membership check fails for everything. The pre-v16 code in
   frappe/desk/desktop.py got this right:
   `allowed_domains = [None, *frappe.get_active_domains()]` ("adding None to
   allowed_domains to include pages without domain restriction").

2. workspace_sidebar.py `get_can_read_items` builds the user's permissions but
   is missing its `return` — so `self.can_read` is None for every sidebar
   consumer. desktop.py's IDENTICAL helper ends with `return self.user.can_read`
   (which is why workspace pages filter correctly and sidebars don't).

Fix (this patch):
    (1) Include NULL/empty restrict_to_domain in both cache builders' IN-filter —
    domain-TAGGED entities keep their gating (a Retail-only page stays hidden
    while Retail is inactive). (2) Add the missing return, mirroring desktop.py.
    The caches' sole consumer is desk_views.py (verified by grep over the pinned
    bench), and `user_perm_can_read` cached None was rebuilt on every call, so no
    stale-cache hazard — but flush redis / clear-cache after deploy anyway.

Usage (run inside the image build, against the baked frappe app):
    python3 frappe_sidebar_visibility.py /home/frappe/frappe-bench

Idempotent (re-run = no-op), drift-guarded (SystemExit if a file shape moved;
nothing is written unless every un-applied block matches exactly), and verifies
the results compile. DROP when upstream fixes these. First shipped to prod as
v16-prod-178 (2026-08-25).
"""
import os
import py_compile
import sys

MARKER_CACHE = "NexumAir patch: domain-allowed cache"
MARKER_RETURN = "NexumAir patch: sidebar visibility"

OLD_DOCTYPE = (
    "\tactive_domains = frappe.get_active_domains()\n"
    '\tdoctypes = frappe.get_all("DocType", filters={"restrict_to_domain": ("IN", active_domains)})\n'
    "\tdoctypes = [doc.name for doc in doctypes]\n"
    '\tfrappe.cache.set_value("domain_restricted_doctypes", doctypes)\n'
)

NEW_DOCTYPE = (
    "\tactive_domains = frappe.get_active_domains()\n"
    "\t# NexumAir patch: domain-allowed cache — include entities with NO domain tag.\n"
    "\t# is_item_allowed (frappe/desk/desk_views.py) requires membership in this cache,\n"
    "\t# so leaving NULL-domain rows out hides every ordinary doctype/page sidebar link\n"
    "\t# from non-Administrator users (v16 regression vs the old desktop.py, which used\n"
    "\t# allowed_domains = [None, *active_domains]). Drop when fixed upstream.\n"
    '\tallowed_domains = [None, "", *active_domains]\n'
    '\tdoctypes = frappe.get_all("DocType", filters={"restrict_to_domain": ("IN", allowed_domains)})\n'
    "\tdoctypes = [doc.name for doc in doctypes]\n"
    '\tfrappe.cache.set_value("domain_restricted_doctypes", doctypes)\n'
)

OLD_PAGE = (
    "\tactive_domains = frappe.get_active_domains()\n"
    '\tpages = frappe.get_all("Page", filters={"restrict_to_domain": ("IN", active_domains)})\n'
    "\tpages = [page.name for page in pages]\n"
    '\tfrappe.cache.set_value("domain_restricted_pages", pages)\n'
)

NEW_PAGE = (
    "\tactive_domains = frappe.get_active_domains()\n"
    "\t# NexumAir patch: domain-allowed cache — see build_domain_restricted_doctype_cache.\n"
    '\tallowed_domains = [None, "", *active_domains]\n'
    '\tpages = frappe.get_all("Page", filters={"restrict_to_domain": ("IN", allowed_domains)})\n'
    "\tpages = [page.name for page in pages]\n"
    '\tfrappe.cache.set_value("domain_restricted_pages", pages)\n'
)

OLD_CAN_READ = (
    "\tdef get_can_read_items(self):\n"
    "\t\tif not self.user.can_read:\n"
    "\t\t\tself.user.build_permissions()\n"
)

NEW_CAN_READ = (
    "\tdef get_can_read_items(self):\n"
    "\t\tif not self.user.can_read:\n"
    "\t\t\tself.user.build_permissions()\n"
    "\t\t# NexumAir patch: sidebar visibility — the missing return left `can_read`\n"
    "\t\t# as None for every sidebar consumer, hiding all DocType sidebar links from\n"
    "\t\t# non-Administrator users. desktop.py's identical helper returns it (the\n"
    "\t\t# proven in-tree behavior). Drop when fixed upstream.\n"
    "\t\treturn self.user.can_read\n"
)

FILES = (
    (
        "apps/frappe/frappe/cache_manager.py",
        MARKER_CACHE,
        ((OLD_DOCTYPE, NEW_DOCTYPE, "build_domain_restricted_doctype_cache"),
         (OLD_PAGE, NEW_PAGE, "build_domain_restricted_page_cache")),
    ),
    (
        "apps/frappe/frappe/desk/doctype/workspace_sidebar/workspace_sidebar.py",
        MARKER_RETURN,
        ((OLD_CAN_READ, NEW_CAN_READ, "get_can_read_items"),),
    ),
)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: frappe_sidebar_visibility.py <bench-root>")
    bench = sys.argv[1]

    # Pass 1: validate every file (drift-guard BEFORE any write).
    plans = []
    for rel, marker, blocks in FILES:
        path = os.path.join(bench, rel)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        if marker in src:
            # The marker only ever exists in our inserted comment, so its presence means
            # this file is already patched. (Do NOT additionally test for the OLD blocks:
            # OLD_CAN_READ is a strict prefix of NEW_CAN_READ, so it still matches after
            # patching and would cause a double-apply.)
            plans.append((path, None))
            continue
        for old, _new, what in blocks:
            n = src.count(old)
            if n != 1:
                raise SystemExit(
                    f"frappe_sidebar_visibility: DRIFT — expected exactly 1 occurrence of "
                    f"the {what} block in {path}, found {n}. Re-vet the patch against this "
                    f"frappe version before shipping; nothing was changed."
                )
        plans.append((path, (src, blocks)))

    # Pass 2: apply.
    for path, plan in plans:
        if plan is None:
            print(f"frappe_sidebar_visibility: already applied — {path} (no-op)")
            py_compile.compile(path, doraise=True)
            continue
        src, blocks = plan
        for old, new, _what in blocks:
            src = src.replace(old, new)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        py_compile.compile(path, doraise=True)
        print(f"frappe_sidebar_visibility: PATCHED {path}")


if __name__ == "__main__":
    main()

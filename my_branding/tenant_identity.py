"""Immutable tenant identity shared by checkout and host entitlement fences.

A missing site is distinct from an existing site with unreadable/unbound identity.
This module never infers identity from a reusable name or old financial records.
"""
import argparse
import json
from pathlib import Path
import re


class UnboundGeneration(ValueError):
    pass


def valid_generation(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value) is not None


def read_generation(sites_root, site, *, require_ready=False):
    if not re.fullmatch(r"[a-z0-9-]+\.nexumair\.com", site):
        raise ValueError("Invalid tenant site")
    directory = Path(sites_root) / site
    try:
        config = json.loads((directory / "site_config.json").read_text())
    except FileNotFoundError:
        if not directory.exists():
            return None
        raise UnboundGeneration("Existing site has no identity configuration") from None
    except (OSError, ValueError) as exc:
        raise UnboundGeneration("Tenant identity configuration cannot be read; retry or reconcile") from exc
    generation = config.get("nexum_tenant_generation") if isinstance(config, dict) else None
    if not valid_generation(generation):
        raise UnboundGeneration("Tenant generation requires reconciliation")
    if require_ready and config.get("nexum_billing_ready", 1) != 1:
        raise UnboundGeneration("Tenant provisioning is not ready for billing")
    return generation


def ensure_current_generation():
    """Migration initializes site identity only, never legacy billing ownership."""
    import uuid
    import frappe
    from frappe.installer import update_site_config

    generation = frappe.conf.get("nexum_tenant_generation")
    if generation is None:
        generation = uuid.uuid4().hex
        update_site_config("nexum_tenant_generation", generation)
        frappe.conf.nexum_tenant_generation = generation
    if not valid_generation(generation):
        raise UnboundGeneration("Invalid existing tenant generation; refusing to replace it")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site")
    parser.add_argument("expected")
    parser.add_argument("--sites-root", default="sites")
    args = parser.parse_args()
    if not valid_generation(args.expected):
        parser.error("An explicit tenant generation is required")
    actual = read_generation(args.sites_root, args.site)
    if actual is None:
        print("Tenant is absent; nothing changed")
        return 3
    if actual != args.expected:
        print("Tenant generation changed; nothing changed")
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

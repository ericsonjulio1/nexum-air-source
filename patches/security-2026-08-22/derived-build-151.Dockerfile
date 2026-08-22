FROM ericsonjulio/erpnext:v16-prod-150
# v16-prod-151: SECURITY — no-version-bump backports onto frappe v16.25.0 /
# erpnext v16.26.2 (same recipe as v16-prod-106 TarSlip). Closes:
#   erpnext GHSA-qq49-v74j-hjh7 CRITICAL SSTI (Process Statement of Accounts)   5f6952b15c
#   erpnext GHSA-6w83-8777-v93q CRITICAL SSTI (RFQ/Contract Tpl/Email Campaign/
#           Delivery Trip/Payment Request/Address template)                      6b45002abc
#   frappe  GHSA-2ph8-x773-8p2x HIGH OAuth2 consent CSRF + auto-approve        eb9c1446ca a0b53599cc
#   frappe  GHSA-cgwf-xgph-hxgm LOW unauthenticated workflow approval          5bf8597781
#   frappe  GHSA-2c6h-wv85-fxvj MEDIUM set_value mass assignment (develop-only) 2a04fae935
#   erpnext GHSA-4j82/m5xh/48wc(+plant floor)/q8wq MEDIUM perm checks         7a606ab91c c7cf9d868b 99f249b1a0 7bc04752fc (+custom guard)
# Deferred (need bench build): GHSA-8pr6-r75h-h8xx (JS bundle XSS), GHSA-mvr5-2j8r-53p4 (banking UI).
# Every file = pin + exactly the security hunks (diff-verified 2026-08-22); in-image
# base files were sha256-identical to the pins before this swap. Pure py/jinja, no asset build.
# Guards: grep-assert each patched marker + py_compile, then the shared idempotent
# patcher (frappe_docker/patches/security-2026-08-22) must report all 16 as already patched.
USER frappe
COPY --chown=frappe:frappe files/erpnext/erpnext/accounts/doctype/process_statement_of_accounts/process_statement_of_accounts.py /home/frappe/frappe-bench/apps/erpnext/erpnext/accounts/doctype/process_statement_of_accounts/process_statement_of_accounts.py
COPY --chown=frappe:frappe files/erpnext/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py /home/frappe/frappe-bench/apps/erpnext/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py
COPY --chown=frappe:frappe files/erpnext/erpnext/crm/doctype/contract_template/contract_template.py /home/frappe/frappe-bench/apps/erpnext/erpnext/crm/doctype/contract_template/contract_template.py
COPY --chown=frappe:frappe files/erpnext/erpnext/crm/doctype/email_campaign/email_campaign.py /home/frappe/frappe-bench/apps/erpnext/erpnext/crm/doctype/email_campaign/email_campaign.py
COPY --chown=frappe:frappe files/erpnext/erpnext/stock/doctype/delivery_trip/delivery_trip.py /home/frappe/frappe-bench/apps/erpnext/erpnext/stock/doctype/delivery_trip/delivery_trip.py
COPY --chown=frappe:frappe files/erpnext/erpnext/accounts/doctype/payment_request/payment_request.py /home/frappe/frappe-bench/apps/erpnext/erpnext/accounts/doctype/payment_request/payment_request.py
COPY --chown=frappe:frappe files/erpnext/erpnext/accounts/custom/address.py /home/frappe/frappe-bench/apps/erpnext/erpnext/accounts/custom/address.py
COPY --chown=frappe:frappe files/erpnext/erpnext/stock/get_item_details.py /home/frappe/frappe-bench/apps/erpnext/erpnext/stock/get_item_details.py
COPY --chown=frappe:frappe files/erpnext/erpnext/controllers/item_variant.py /home/frappe/frappe-bench/apps/erpnext/erpnext/controllers/item_variant.py
COPY --chown=frappe:frappe files/erpnext/erpnext/assets/doctype/asset_capitalization/asset_capitalization.py /home/frappe/frappe-bench/apps/erpnext/erpnext/assets/doctype/asset_capitalization/asset_capitalization.py
COPY --chown=frappe:frappe files/erpnext/erpnext/manufacturing/doctype/plant_floor/plant_floor.py /home/frappe/frappe-bench/apps/erpnext/erpnext/manufacturing/doctype/plant_floor/plant_floor.py
COPY --chown=frappe:frappe files/frappe/frappe/integrations/oauth2.py /home/frappe/frappe-bench/apps/frappe/frappe/integrations/oauth2.py
COPY --chown=frappe:frappe files/frappe/frappe/templates/includes/oauth_confirmation.html /home/frappe/frappe-bench/apps/frappe/frappe/templates/includes/oauth_confirmation.html
COPY --chown=frappe:frappe files/frappe/frappe/workflow/doctype/workflow_action/workflow_action.py /home/frappe/frappe-bench/apps/frappe/frappe/workflow/doctype/workflow_action/workflow_action.py
COPY --chown=frappe:frappe files/frappe/frappe/www/confirm_workflow_action.html /home/frappe/frappe-bench/apps/frappe/frappe/www/confirm_workflow_action.html
COPY --chown=frappe:frappe files/frappe/frappe/client.py /home/frappe/frappe-bench/apps/frappe/frappe/client.py
RUN set -e; A=/home/frappe/frappe-bench/apps \
 && grep -qF -- "validate_template(self.subject, restrict_globals=True)" $A/erpnext/erpnext/accounts/doctype/process_statement_of_accounts/process_statement_of_accounts.py \
 && grep -qF -- "frappe.render_template(doc.body, context, restrict_globals=True)" $A/erpnext/erpnext/accounts/doctype/process_statement_of_accounts/process_statement_of_accounts.py \
 && python3 -m py_compile $A/erpnext/erpnext/accounts/doctype/process_statement_of_accounts/process_statement_of_accounts.py \
 && grep -qF -- "frappe.render_template(message_template, doc_args, restrict_globals=True)" $A/erpnext/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py \
 && grep -qF -- "frappe.render_template(subject_source, doc_args, restrict_globals=True)" $A/erpnext/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py \
 && python3 -m py_compile $A/erpnext/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py \
 && grep -qF -- "validate_template(self.contract_terms, restrict_globals=True)" $A/erpnext/erpnext/crm/doctype/contract_template/contract_template.py \
 && grep -qF -- "frappe.render_template(contract_template.contract_terms, doc, restrict_globals=True)" $A/erpnext/erpnext/crm/doctype/contract_template/contract_template.py \
 && python3 -m py_compile $A/erpnext/erpnext/crm/doctype/contract_template/contract_template.py \
 && grep -qF -- "frappe.render_template(email_template.response_, context, restrict_globals=True)" $A/erpnext/erpnext/crm/doctype/email_campaign/email_campaign.py \
 && python3 -m py_compile $A/erpnext/erpnext/crm/doctype/email_campaign/email_campaign.py \
 && grep -qF -- "frappe.render_template(dispatch_template.response, context, restrict_globals=True)" $A/erpnext/erpnext/stock/doctype/delivery_trip/delivery_trip.py \
 && python3 -m py_compile $A/erpnext/erpnext/stock/doctype/delivery_trip/delivery_trip.py \
 && grep -qF -- "frappe.render_template(self.message, context, restrict_globals=True)" $A/erpnext/erpnext/accounts/doctype/payment_request/payment_request.py \
 && ! grep -qF -- "frappe.render_template(self.message, context)" $A/erpnext/erpnext/accounts/doctype/payment_request/payment_request.py \
 && python3 -m py_compile $A/erpnext/erpnext/accounts/doctype/payment_request/payment_request.py \
 && grep -qF -- "address_template, address_as_dict, restrict_globals=True" $A/erpnext/erpnext/accounts/custom/address.py \
 && python3 -m py_compile $A/erpnext/erpnext/accounts/custom/address.py \
 && grep -qF -- "item.check_permission()" $A/erpnext/erpnext/stock/get_item_details.py \
 && python3 -m py_compile $A/erpnext/erpnext/stock/get_item_details.py \
 && grep -qF -- "frappe.has_permission(\"Item\", ptype=\"create\", throw=True)" $A/erpnext/erpnext/controllers/item_variant.py \
 && python3 -m py_compile $A/erpnext/erpnext/controllers/item_variant.py \
 && grep -qF -- "frappe.has_permission(\"Stock Ledger Entry\", throw=True)" $A/erpnext/erpnext/assets/doctype/asset_capitalization/asset_capitalization.py \
 && grep -qF -- "frappe.has_permission(\"Warehouse\", doc=args.warehouse, throw=True)" $A/erpnext/erpnext/assets/doctype/asset_capitalization/asset_capitalization.py \
 && python3 -m py_compile $A/erpnext/erpnext/assets/doctype/asset_capitalization/asset_capitalization.py \
 && grep -qF -- "frappe.has_permission(\"Warehouse\", doc=warehouse, throw=True)" $A/erpnext/erpnext/manufacturing/doctype/plant_floor/plant_floor.py \
 && python3 -m py_compile $A/erpnext/erpnext/manufacturing/doctype/plant_floor/plant_floor.py \
 && grep -qF -- "from frappe.sessions import get_csrf_token" $A/frappe/frappe/integrations/oauth2.py \
 && grep -qF -- "\"csrf_token\": get_csrf_token()" $A/frappe/frappe/integrations/oauth2.py \
 && (grep -A1 -F -- "@frappe.whitelist(methods=[\"POST\"])" $A/frappe/frappe/integrations/oauth2.py | grep -qF "def approve(") \
 && python3 -m py_compile $A/frappe/frappe/integrations/oauth2.py \
 && grep -qF -- "<input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token }}\">" $A/frappe/frappe/templates/includes/oauth_confirmation.html \
 && ! grep -qF -- "window.location.replace" $A/frappe/frappe/templates/includes/oauth_confirmation.html \
 && ! grep -qF -- "frappe.set_user(user)" $A/frappe/frappe/workflow/doctype/workflow_action/workflow_action.py \
 && ! (grep -A1 -F -- "@frappe.whitelist(allow_guest=True)" $A/frappe/frappe/workflow/doctype/workflow_action/workflow_action.py | grep -qF "def confirm_action") \
 && (grep -A1 -F -- "@frappe.whitelist()" $A/frappe/frappe/workflow/doctype/workflow_action/workflow_action.py | grep -qF "def confirm_action") \
 && python3 -m py_compile $A/frappe/frappe/workflow/doctype/workflow_action/workflow_action.py \
 && grep -qF -- "{% if is_guest %}" $A/frappe/frappe/www/confirm_workflow_action.html \
 && grep -qF -- "forbidden = set(frappe.model.default_fields + frappe.model.child_table_fields)" $A/frappe/frappe/client.py \
 && ! grep -qF -- "if fieldname in (frappe.model.default_fields + frappe.model.child_table_fields):" $A/frappe/frappe/client.py \
 && python3 -m py_compile $A/frappe/frappe/client.py \
 && echo "security-2026-08-22 markers + compile verified in image"
COPY --chown=frappe:frappe patcher/ /tmp/patches/security-2026-08-22/
COPY --chown=frappe:frappe files/ /tmp/patches/security-2026-08-22/files/
RUN python3 /tmp/patches/security-2026-08-22/apply.py --verify /home/frappe/frappe-bench \
 && python3 /tmp/patches/security-2026-08-22/apply.py /home/frappe/frappe-bench \
 && rm -rf /tmp/patches

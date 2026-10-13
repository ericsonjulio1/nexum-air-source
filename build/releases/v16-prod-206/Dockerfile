ARG BASE_IMAGE=ericsonjulio/erpnext@sha256:c604df209f8e40f44c13e92dae9a12754aa18034ede6c693bbb3df9e22ed0d73
FROM ${BASE_IMAGE}
USER frappe
WORKDIR /home/frappe/frappe-bench
ENV NODE_OPTIONS=--max-old-space-size=2560
RUN rm -rf apps/frappe apps/erpnext apps/hrms apps/crm apps/helpdesk apps/print_designer apps/insights
COPY --chown=frappe:frappe apps/ apps/
COPY --chown=frappe:frappe security/ /tmp/upgrade-206/security/
RUN uv pip install --python env/bin/python -e apps/frappe -e apps/erpnext -e apps/hrms -e apps/crm -e apps/helpdesk -e apps/print_designer -e apps/insights 'litellm==1.95.0'
RUN uv pip check --python env/bin/python
RUN yarn --cwd apps/frappe install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/frappe/ui install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/erpnext install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/erpnext/banking install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/hrms install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/hrms/frontend install --frozen-lockfile --network-timeout 300000 && yarn --cwd apps/hrms/roster install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/crm install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/crm/frontend install --frozen-lockfile --network-timeout 300000
COPY --chown=frappe:frappe locks/helpdesk/yarn.lock apps/helpdesk/desk/yarn.lock
RUN yarn --cwd apps/helpdesk install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/helpdesk/desk install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/print_designer install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/insights install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/insights/frontend install --frozen-lockfile --network-timeout 300000
RUN mkdir -p sites/assets && cp -a assets/. sites/assets/
RUN bench build --app frappe --production --force
RUN bench build --app erpnext --production --force
RUN bench build --app hrms --production --force
RUN bench build --app print_designer --production --force
RUN bench build --app crm --production --force
RUN env/bin/python -c 'import json; from pathlib import Path; p=Path("sites/common_site_config.json"); c=json.loads(p.read_text()); c["socketio_port"]=9000; p.write_text(json.dumps(c))'
RUN bench build --app helpdesk --production --force
RUN bench build --app insights --production --force
COPY --chown=frappe:frappe compatibility/ /tmp/upgrade-206/compatibility/
RUN env/bin/python /tmp/upgrade-206/compatibility/sidebar_code_only.py /home/frappe/frappe-bench
RUN env/bin/python /tmp/upgrade-206/compatibility/migrate_missing_apps.py /home/frappe/frappe-bench
# Print Designer installation reuses the maintained system Chromium.
RUN mkdir -p chromium/chrome-linux && ln -s /usr/bin/chromium-headless-shell chromium/chrome-linux/headless_shell
RUN env/bin/python /tmp/upgrade-206/compatibility/web_form_attachments.py /home/frappe/frappe-bench
RUN env/bin/python /tmp/upgrade-206/compatibility/gameplan_queries.py /home/frappe/frappe-bench
COPY --chown=frappe:frappe custom/my_branding/ apps/my_branding/
COPY --chown=frappe:frappe custom/eam/ apps/eam/
RUN bench build --app my_branding --app eam --production --force
RUN env/bin/python /tmp/upgrade-206/security/apply.py --verify /home/frappe/frappe-bench
RUN rm -rf assets && cp -a sites/assets assets && rm -rf sites/assets
COPY --chmod=755 compatibility/entrypoint.sh /usr/local/bin/entrypoint.sh
LABEL com.nexumair.release="v16-prod-206" com.nexumair.framework.release="v16-prod-206" com.nexumair.frappe.version="16.51.1" com.nexumair.erpnext.version="16.50.0"
LABEL com.nexumair.branding.commit="3e4449ee9608542d96372cc05bb8e6eb8a9abe4c" com.nexumair.eam.commit="d902e4ef5d4bd6037987f1379313b1d1dc3a8b8f"
LABEL com.nexumair.my_branding.commit="3e4449ee9608542d96372cc05bb8e6eb8a9abe4c" com.nexumair.my_branding.source="v16-prod-206" com.nexumair.my_branding_sha="3e4449e" com.nexumair.eam_sha="d902e4e" com.nexumair.security.hrms_ghsa_jfmr="upstream"

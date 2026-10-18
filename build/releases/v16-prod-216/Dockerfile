FROM ericsonjulio/erpnext@sha256:60690202d8452139c5a2807f6df86254c5f0a477e130e18f7252debf2d4bcf43
USER frappe
WORKDIR /home/frappe/frappe-bench
ENV NODE_OPTIONS=--max-old-space-size=2560
RUN rm -rf apps/frappe apps/erpnext apps/hrms apps/crm apps/helpdesk apps/insights
COPY --chown=frappe:frappe apps/ apps/
COPY --chown=frappe:frappe security/ /tmp/upgrade-216/security/
RUN uv pip install --python env/bin/python -e apps/frappe -e apps/erpnext -e apps/hrms -e apps/crm -e apps/helpdesk -e apps/insights 'litellm==1.95.0'
RUN uv pip check --python env/bin/python
RUN yarn --cwd apps/frappe install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/frappe/ui install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/erpnext install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/erpnext/banking install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/hrms install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/hrms/frontend install --frozen-lockfile --network-timeout 300000 && yarn --cwd apps/hrms/roster install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/crm install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/crm/frontend install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/helpdesk install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/helpdesk/desk install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/insights install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/insights/frontend install --frozen-lockfile --network-timeout 300000
COPY --chown=frappe:frappe patch-dependencies.py /tmp/upgrade-216/patch-dependencies.py
RUN env/bin/python /tmp/upgrade-216/patch-dependencies.py /home/frappe/frappe-bench
RUN env/bin/python /tmp/upgrade-216/security/apply.py --verify /home/frappe/frappe-bench
RUN mkdir -p sites/assets && cp -a assets/. sites/assets/
RUN bench build --app frappe --production --force
RUN bench build --app erpnext --production --force
RUN bench build --app hrms --production --force
RUN bench build --app crm --production --force
RUN bench build --app helpdesk --production --force
RUN bench build --app insights --production --force
RUN rm -rf assets && cp -a sites/assets assets && rm -rf sites/assets
COPY --chown=frappe:frappe patch-migration-cache.py /tmp/upgrade-216/patch-migration-cache.py
RUN env/bin/python /tmp/upgrade-216/patch-migration-cache.py
COPY --chown=frappe:frappe eam-tests/ apps/eam/eam/tests/
LABEL com.nexumair.release="v16-prod-216" com.nexumair.framework.release="v16-prod-216" com.nexumair.frappe.version="16.52.0" com.nexumair.erpnext.version="16.51.1"
LABEL com.nexumair.branding.commit="96c6e48fafcb3b8e1fb6f7f51f762c596c138548" com.nexumair.eam.commit="05c867e650eadb181cf379ac88a75c555a1d2c0f"

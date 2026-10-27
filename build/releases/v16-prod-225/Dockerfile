# Native Python packages are compiled in a disposable stage. Only verified
# wheels are mounted into the final install; compiler/Rust tools never ship.
FROM rust:1.92.0-slim-bookworm@sha256:bde68fd7fcfddd031989211a8f565421857aed3bac848f9c429a98d8da7bae31 AS rust-build-tools
FROM ericsonjulio/erpnext@sha256:94ee3b75c13168d36dcdab8cb4fb69db7a80e64c9c40f8764d1f98fca847ea32 AS python-wheels
USER root
COPY --from=rust-build-tools /usr/local/cargo /usr/local/cargo
COPY --from=rust-build-tools /usr/local/rustup /usr/local/rustup
ENV CARGO_HOME=/usr/local/cargo RUSTUP_HOME=/usr/local/rustup CARGO_BUILD_JOBS=2 PATH=/usr/local/cargo/bin:$PATH
RUN apt-get update && apt-get install --no-install-recommends -y build-essential pkg-config libmariadb-dev
COPY maintenance-python-security.lock python-security.lock verify-python-lock.py /tmp/nexum-wheel-build/
RUN uv pip install --python /usr/local/bin/python --require-hashes --reinstall --no-cache --no-deps -r /tmp/nexum-wheel-build/maintenance-python-security.lock
RUN /usr/local/bin/python -m pip wheel --no-cache-dir --require-hashes --no-deps --wheel-dir /opt/nexum-wheels -r /tmp/nexum-wheel-build/python-security.lock
COPY make-wheel-lock.py /tmp/nexum-wheel-build/
RUN /usr/local/bin/python -I -B /tmp/nexum-wheel-build/make-wheel-lock.py /opt/nexum-wheels /tmp/nexum-wheel-build/python-security.lock

FROM ericsonjulio/erpnext@sha256:94ee3b75c13168d36dcdab8cb4fb69db7a80e64c9c40f8764d1f98fca847ea32
USER frappe
WORKDIR /home/frappe/frappe-bench
ENV NODE_OPTIONS=--max-old-space-size=2560 COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN rm -rf apps/frappe apps/erpnext apps/hrms apps/crm apps/helpdesk apps/insights apps/drive apps/telephony apps/my_branding
COPY --chown=frappe:frappe apps/ apps/
COPY --chown=frappe:frappe security/ /tmp/upgrade-225/security/
RUN uv pip install --python env/bin/python -e apps/frappe -e apps/erpnext -e apps/hrms -e apps/crm -e apps/helpdesk -e apps/insights -e apps/drive -e apps/telephony -e apps/my_branding 'litellm==1.95.0'
RUN uv pip check --python env/bin/python
RUN yarn --cwd apps/frappe install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/frappe/ui install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/erpnext install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/erpnext/banking install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/hrms install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/hrms/frontend install --frozen-lockfile --network-timeout 300000 && yarn --cwd apps/hrms/roster install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/crm install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/crm/frontend install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/helpdesk install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/helpdesk/desk install --frozen-lockfile --network-timeout 300000
RUN yarn --cwd apps/insights install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/insights/frontend install --frozen-lockfile --network-timeout 300000
RUN corepack prepare pnpm@10.34.9 --activate && pnpm --dir apps/drive/frontend install --frozen-lockfile
COPY --chown=frappe:frappe patch-dependencies.py /tmp/upgrade-225/patch-dependencies.py
RUN env/bin/python /tmp/upgrade-225/patch-dependencies.py /home/frappe/frappe-bench
RUN env/bin/python /tmp/upgrade-225/security/apply.py --verify /home/frappe/frappe-bench
RUN mkdir -p sites/assets && cp -a assets/. sites/assets/
RUN bench build --app frappe --production --force
RUN bench build --app erpnext --production --force
RUN bench build --app hrms --production --force
RUN bench build --app crm --production --force
RUN bench build --app helpdesk --production --force
RUN bench build --app insights --production --force
# Drive uses pnpm; Frappe's app-build dispatcher always invokes Yarn. Build both
# asset layers explicitly, then let Bench index them and compile translations.
RUN yarn --cwd apps/frappe run production --apps drive && pnpm --dir apps/drive/frontend build && bench build --app drive --production --force --using-cached
RUN bench build --app my_branding --production --force
RUN rm -rf assets && cp -a sites/assets assets && rm -rf sites/assets
COPY --chown=frappe:frappe patch-migration-cache.py /tmp/upgrade-225/patch-migration-cache.py
RUN env/bin/python /tmp/upgrade-225/patch-migration-cache.py
LABEL com.nexumair.release="v16-prod-225" com.nexumair.framework.release="v16-prod-225" com.nexumair.frappe.version="16.53.0" com.nexumair.erpnext.version="16.52.1"
LABEL com.nexumair.branding.commit="127f4934b1f408678b2ad0ed3c1b08fb0a6b07b8" com.nexumair.my_branding.commit="127f4934b1f408678b2ad0ed3c1b08fb0a6b07b8" com.nexumair.my_branding.source="v16-prod-225" com.nexumair.my_branding_sha="127f493" com.nexumair.eam.commit="9de5ada9a7e57e5fb3db91f02bb93c7c67a81881"
COPY --chown=frappe:frappe patch-mcp-migration.py /tmp/upgrade-225/patch-mcp-migration.py
RUN env/bin/python /tmp/upgrade-225/patch-mcp-migration.py
COPY --chown=frappe:frappe patch-drive-menu.py /tmp/upgrade-225/patch-drive-menu.py
RUN env/bin/python /tmp/upgrade-225/patch-drive-menu.py && mkdir -p sites/assets && cp -a assets/. sites/assets/ && yarn --cwd apps/frappe run production --apps drive && pnpm --dir apps/drive/frontend build && bench build --app drive --production --force --using-cached && rm -rf assets && cp -a sites/assets assets && rm -rf sites/assets

# Dependency security remediation and public bulk-PDF option containment.
COPY --chown=frappe:frappe python-security.patch python-security.lock /tmp/upgrade-225/
RUN git apply --check /tmp/upgrade-225/python-security.patch && git apply /tmp/upgrade-225/python-security.patch
COPY --from=python-wheels /opt/nexum-wheels/wheels.lock /tmp/upgrade-225/runtime-wheels.lock
COPY --from=python-wheels /opt/nexum-wheels/wheels.json /tmp/upgrade-225/runtime-wheels.json
RUN --mount=from=python-wheels,source=/opt/nexum-wheels,target=/opt/nexum-wheels,ro uv pip uninstall --python env/bin/python litellm && uv pip install --python env/bin/python --require-hashes --reinstall --no-cache --no-deps --no-index --find-links /opt/nexum-wheels -r /tmp/upgrade-225/runtime-wheels.lock
RUN uv pip install --python env/bin/python --no-build-isolation --no-deps -e apps/frappe -e apps/telephony && uv pip check --python env/bin/python

COPY --chown=frappe:frappe verify-python-lock.py /tmp/upgrade-225/
RUN env/bin/python -I -B /tmp/upgrade-225/verify-python-lock.py /tmp/upgrade-225/python-security.lock

# Bench has a separate Python environment; secure and lock that inventory too.
COPY --chown=frappe:frappe maintenance-python-security.lock /tmp/upgrade-225/
USER root
RUN uv pip install --python /usr/local/bin/python --require-hashes --reinstall --no-cache --no-deps -r /tmp/upgrade-225/maintenance-python-security.lock && uv pip check --python /usr/local/bin/python
RUN /usr/local/bin/python -I -B /tmp/upgrade-225/verify-python-lock.py /tmp/upgrade-225/maintenance-python-security.lock --maintenance
USER frappe
RUN bench --version && uv pip check --python env/bin/python

# Match the fixed certifi/uv trust policy in stdlib/OpenSSL and Node too.
COPY --chown=root:root remove-compromised-roots.py /tmp/upgrade-225/
USER root
RUN /usr/local/bin/python -I -B /tmp/upgrade-225/remove-compromised-roots.py
USER frappe
ENV NODE_OPTIONS="--max-old-space-size=2560 --use-openssl-ca"

COPY --chown=root:root align-pip-ca.py /tmp/upgrade-225/
USER root
RUN /usr/local/bin/python -I -B /tmp/upgrade-225/align-pip-ca.py
USER frappe

# Full-framework v225 RC7 workflow, rebased on live RC3 to retain its runtime fixes.
FROM ericsonjulio/erpnext@sha256:ae924799fb695f14ac5a4bfe74eb8844380e6fe4c4400509a43b38ac075d035e
USER frappe
WORKDIR /home/frappe/frappe-bench
COPY --chown=frappe:frappe v227-tools/ /tmp/upgrade-227/
RUN env/bin/python -I -B /tmp/upgrade-227/verify-inherited.py before && env/bin/python -I -B /tmp/upgrade-227/verify-retained.py
RUN rm -rf apps/frappe apps/erpnext apps/hrms apps/crm apps/helpdesk apps/drive apps/eam apps/my_branding
COPY --chown=frappe:frappe apps/ apps/
RUN env/bin/python -I -B /tmp/upgrade-227/apply-source.py /home/frappe/frappe-bench --verify
# Only editable app metadata changes; the RC3 non-app inventory and locks stay fixed.
RUN UV_NO_CACHE=1 PYTHONDONTWRITEBYTECODE=1 uv pip install --python env/bin/python --no-deps --no-build-isolation --no-index -e apps/frappe -e apps/erpnext -e apps/hrms -e apps/crm -e apps/helpdesk -e apps/drive -e apps/eam -e apps/my_branding && UV_NO_CACHE=1 uv pip check --python env/bin/python
RUN env/bin/python -I -B /tmp/upgrade-227/verify-inherited.py after
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-227/build-state/tmp TMP=/tmp/upgrade-227/build-state/tmp TEMP=/tmp/upgrade-227/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-227/build-state/yarn-cache npm_config_cache=/tmp/upgrade-227/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-227/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-227/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-227/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-227/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/frappe install --frozen-lockfile --network-timeout 300000 && yarn --cwd apps/frappe/ui install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-227/build-state/tmp TMP=/tmp/upgrade-227/build-state/tmp TEMP=/tmp/upgrade-227/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-227/build-state/yarn-cache npm_config_cache=/tmp/upgrade-227/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-227/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-227/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-227/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-227/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/erpnext install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/erpnext/banking install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-227/build-state/tmp TMP=/tmp/upgrade-227/build-state/tmp TEMP=/tmp/upgrade-227/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-227/build-state/yarn-cache npm_config_cache=/tmp/upgrade-227/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-227/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-227/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-227/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-227/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/hrms install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/hrms/frontend install --frozen-lockfile --network-timeout 300000 && yarn --cwd apps/hrms/roster install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-227/build-state/tmp TMP=/tmp/upgrade-227/build-state/tmp TEMP=/tmp/upgrade-227/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-227/build-state/yarn-cache npm_config_cache=/tmp/upgrade-227/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-227/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-227/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-227/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-227/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/crm install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/crm/frontend install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-227/build-state/tmp TMP=/tmp/upgrade-227/build-state/tmp TEMP=/tmp/upgrade-227/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-227/build-state/yarn-cache npm_config_cache=/tmp/upgrade-227/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-227/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-227/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-227/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-227/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/helpdesk install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/helpdesk/desk install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-227/build-state/tmp TMP=/tmp/upgrade-227/build-state/tmp TEMP=/tmp/upgrade-227/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-227/build-state/yarn-cache npm_config_cache=/tmp/upgrade-227/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-227/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-227/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-227/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-227/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    test "$(pnpm --version)" = 10.34.9 && pnpm --dir apps/drive/frontend --store-dir /tmp/upgrade-227/build-state/pnpm-store install --frozen-lockfile
RUN env/bin/python -I -B /tmp/upgrade-227/patch-installed-dependencies.py /home/frappe/frappe-bench && env/bin/python -I -B /tmp/upgrade-227/patch-installed-dependencies.py /home/frappe/frappe-bench --verify
RUN env/bin/python -I -B /tmp/upgrade-227/patchers/security/apply.py --verify /home/frappe/frappe-bench
RUN test ! -e sites/assets && mkdir -p sites/assets && cp -a assets/. sites/assets/
# Preserve inherited logs and residue; every build tool uses removable private state.
# Build replaced apps only; retained apps keep their exact inherited output.
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-227/build-state/tmp TMP=/tmp/upgrade-227/build-state/tmp TEMP=/tmp/upgrade-227/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-227/build-state/yarn-cache npm_config_cache=/tmp/upgrade-227/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-227/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-227/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-227/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-227/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    scratch="$(mktemp -d "$TMPDIR/bench-build.XXXXXX")"; \
    test -d logs && test ! -L logs; mv logs "$scratch/original-logs"; \
    restore() { result="$?"; trap - 0; rm -rf logs; mv "$scratch/original-logs" logs; rm -rf "$scratch"; exit "$result"; }; \
    trap restore 0; mkdir logs; \
    export PYTHONDONTWRITEBYTECODE=1 UV_NO_CACHE=1; \
    for app in frappe erpnext hrms crm helpdesk; do bench build --app "$app" --production --force; if [ "$app" = crm ]; then env/bin/python -I -B /tmp/upgrade-227/patchers/crm-pulse/verify.py --verify /home/frappe/frappe-bench; fi; done; \
    yarn --cwd apps/frappe run production --apps drive; pnpm --dir apps/drive/frontend build; bench build --app drive --production --force --using-cached; \
    bench build --app eam --production --force; bench build --app my_branding --production --force; bench --version
RUN rm -rf /tmp/upgrade-227/build-state && rm -rf assets && cp -a sites/assets assets && rm -rf sites/assets
RUN env/bin/python -I -B /tmp/upgrade-227/apply-source.py /home/frappe/frappe-bench --verify && env/bin/python -I -B /tmp/upgrade-227/verify-inherited.py after
LABEL com.nexumair.release="v16-prod-227" com.nexumair.framework.release="v16-prod-227" \
      com.nexumair.frappe.version="16.54.0" com.nexumair.erpnext.version="16.53.0" \
      com.nexumair.base.digest="sha256:ae924799fb695f14ac5a4bfe74eb8844380e6fe4c4400509a43b38ac075d035e" \
      com.nexumair.my_branding.source="v16-prod-227" com.nexumair.branding.commit="66897f3a946e5a8034720d000313bc874c19291c" \
      com.nexumair.my_branding.commit="66897f3a946e5a8034720d000313bc874c19291c" com.nexumair.eam.commit="c65980f7fbd995759982952e2bf564a20038279a" \
      com.nexumair.my_branding_sha="66897f3" com.nexumair.eam_sha="c65980f"

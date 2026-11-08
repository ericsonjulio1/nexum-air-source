# Full-framework v225 RC7 workflow, rebased on the live v227 image (v227 itself rebased on v226 RC3) to retain its runtime fixes.
FROM ericsonjulio/erpnext@sha256:1c287bb2682e08199cd604462091c72882afc6ebe020b5504e3f0e464919b952
USER frappe
WORKDIR /home/frappe/frappe-bench
COPY --chown=frappe:frappe v228-tools/ /tmp/upgrade-228/
RUN env/bin/python -I -B /tmp/upgrade-228/verify-dependencies.py before --verify-lock /tmp/upgrade-228/patchers/verify-python-lock.py --lock-before /tmp/upgrade-228/python-security-v227.lock --lock-after /tmp/upgrade-228/python-security-v228.lock --lock-maintenance /tmp/upgrade-228/maintenance-python-security.lock && env/bin/python -I -B /tmp/upgrade-228/verify-retained.py
RUN rm -rf apps/frappe apps/erpnext apps/hrms apps/crm apps/helpdesk apps/drive apps/eam apps/my_branding
COPY --chown=frappe:frappe apps/ apps/
RUN env/bin/python -I -B /tmp/upgrade-228/apply-source.py /home/frappe/frappe-bench --verify
# v228 dependency delta (recipe/deps; DEPS-r1): exactly four hash-pinned wheels (filelock, fonttools, oauthlib replaced; plutoprint added),
# installed offline in the SAME RUN as the editable apps and before the single `uv pip check` (the old editable frappe metadata, filelock~=3.20.1,
# would fail the check). Nothing else may change: verify-dependencies.py `after` proves the exact delta, unchanged bytes elsewhere and faithful wheel installs.
RUN UV_NO_CACHE=1 PYTHONDONTWRITEBYTECODE=1 uv pip install --python env/bin/python --no-deps --no-index --find-links /tmp/upgrade-228/wheels --require-hashes --only-binary :all: --reinstall -r /tmp/upgrade-228/python-delta-wheels.lock && UV_NO_CACHE=1 PYTHONDONTWRITEBYTECODE=1 uv pip install --python env/bin/python --no-deps --no-build-isolation --no-index -e apps/frappe -e apps/erpnext -e apps/hrms -e apps/crm -e apps/helpdesk -e apps/drive -e apps/eam -e apps/my_branding && UV_NO_CACHE=1 uv pip check --python env/bin/python
RUN env/bin/python -I -B /tmp/upgrade-228/verify-dependencies.py after --verify-lock /tmp/upgrade-228/patchers/verify-python-lock.py --lock-before /tmp/upgrade-228/python-security-v227.lock --lock-after /tmp/upgrade-228/python-security-v228.lock --lock-maintenance /tmp/upgrade-228/maintenance-python-security.lock
# Native gate: the delta distributions import on this image (plutoprint ships bundled native libraries) at exactly the reviewed versions.
RUN env/bin/python -I -B -c "import plutoprint, fontTools, filelock, oauthlib, importlib.metadata as m; v = {n: m.version(n) for n in ('filelock', 'fonttools', 'oauthlib', 'plutoprint')}; assert v == {'filelock': '4.2.4', 'fonttools': '4.68.0', 'oauthlib': '4.0.1', 'plutoprint': '0.22.0'}, v; assert filelock.__version__ == v['filelock'] and fontTools.version == v['fonttools'] and oauthlib.__version__ == v['oauthlib'], (filelock.__version__, fontTools.version, oauthlib.__version__); assert filelock.FileLock.__name__ == 'UnixFileLock'; print(v)"
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-228/build-state/tmp TMP=/tmp/upgrade-228/build-state/tmp TEMP=/tmp/upgrade-228/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-228/build-state/yarn-cache npm_config_cache=/tmp/upgrade-228/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-228/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-228/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-228/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-228/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/frappe install --frozen-lockfile --network-timeout 300000 && yarn --cwd apps/frappe/ui install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-228/build-state/tmp TMP=/tmp/upgrade-228/build-state/tmp TEMP=/tmp/upgrade-228/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-228/build-state/yarn-cache npm_config_cache=/tmp/upgrade-228/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-228/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-228/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-228/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-228/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/erpnext install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/erpnext/banking install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-228/build-state/tmp TMP=/tmp/upgrade-228/build-state/tmp TEMP=/tmp/upgrade-228/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-228/build-state/yarn-cache npm_config_cache=/tmp/upgrade-228/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-228/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-228/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-228/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-228/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/hrms install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/hrms/frontend install --frozen-lockfile --network-timeout 300000 && yarn --cwd apps/hrms/roster install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-228/build-state/tmp TMP=/tmp/upgrade-228/build-state/tmp TEMP=/tmp/upgrade-228/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-228/build-state/yarn-cache npm_config_cache=/tmp/upgrade-228/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-228/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-228/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-228/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-228/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/crm install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/crm/frontend install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-228/build-state/tmp TMP=/tmp/upgrade-228/build-state/tmp TEMP=/tmp/upgrade-228/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-228/build-state/yarn-cache npm_config_cache=/tmp/upgrade-228/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-228/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-228/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-228/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-228/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/helpdesk install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/helpdesk/desk install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-228/build-state/tmp TMP=/tmp/upgrade-228/build-state/tmp TEMP=/tmp/upgrade-228/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-228/build-state/yarn-cache npm_config_cache=/tmp/upgrade-228/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-228/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-228/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-228/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-228/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    test "$(pnpm --version)" = 10.34.9 && pnpm --dir apps/drive/frontend --store-dir /tmp/upgrade-228/build-state/pnpm-store install --frozen-lockfile
RUN env/bin/python -I -B /tmp/upgrade-228/patch-installed-dependencies.py /home/frappe/frappe-bench && env/bin/python -I -B /tmp/upgrade-228/patch-installed-dependencies.py /home/frappe/frappe-bench --verify
RUN env/bin/python -I -B /tmp/upgrade-228/patchers/security/apply.py --verify /home/frappe/frappe-bench
RUN test ! -e sites/assets && mkdir -p sites/assets && cp -a assets/. sites/assets/
# Preserve inherited logs and residue; every build tool uses removable private state.
# Build replaced apps only; retained apps keep their exact inherited output.
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-228/build-state/tmp TMP=/tmp/upgrade-228/build-state/tmp TEMP=/tmp/upgrade-228/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-228/build-state/yarn-cache npm_config_cache=/tmp/upgrade-228/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-228/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-228/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-228/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-228/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    scratch="$(mktemp -d "$TMPDIR/bench-build.XXXXXX")"; \
    test -d logs && test ! -L logs; mv logs "$scratch/original-logs"; \
    restore() { result="$?"; trap - 0; rm -rf logs; mv "$scratch/original-logs" logs; rm -rf "$scratch"; exit "$result"; }; \
    trap restore 0; mkdir logs; \
    export PYTHONDONTWRITEBYTECODE=1 UV_NO_CACHE=1; \
    for app in frappe erpnext hrms crm helpdesk; do bench build --app "$app" --production --force; if [ "$app" = crm ]; then env/bin/python -I -B /tmp/upgrade-228/patchers/crm-pulse/verify.py --verify /home/frappe/frappe-bench; fi; done; \
    yarn --cwd apps/frappe run production --apps drive; pnpm --dir apps/drive/frontend build; bench build --app drive --production --force --using-cached; \
    bench build --app eam --production --force; bench build --app my_branding --production --force; bench --version
RUN rm -rf /tmp/upgrade-228/build-state && rm -rf assets && cp -a sites/assets assets && rm -rf sites/assets
RUN env/bin/python -I -B /tmp/upgrade-228/apply-source.py /home/frappe/frappe-bench --verify && env/bin/python -I -B /tmp/upgrade-228/verify-dependencies.py after --verify-lock /tmp/upgrade-228/patchers/verify-python-lock.py --lock-before /tmp/upgrade-228/python-security-v227.lock --lock-after /tmp/upgrade-228/python-security-v228.lock --lock-maintenance /tmp/upgrade-228/maintenance-python-security.lock
LABEL com.nexumair.release="v16-prod-228" com.nexumair.framework.release="v16-prod-228" \
      com.nexumair.frappe.version="16.55.2" com.nexumair.erpnext.version="16.54.0" \
      com.nexumair.base.digest="sha256:1c287bb2682e08199cd604462091c72882afc6ebe020b5504e3f0e464919b952" \
      com.nexumair.my_branding.source="v16-prod-228" com.nexumair.branding.commit="8cf99edd4da1a666f74de1f1cccedaf9533d2527" \
      com.nexumair.my_branding.commit="8cf99edd4da1a666f74de1f1cccedaf9533d2527" com.nexumair.eam.commit="3146e4f524df673c49524248e9518f495b2fd31b" \
      com.nexumair.my_branding_sha="8cf99ed" com.nexumair.eam_sha="3146e4f"

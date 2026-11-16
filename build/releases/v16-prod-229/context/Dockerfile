# Full-framework v225 RC7 workflow, rebased on the live v228 image (v228 on v227, v227 on v226 RC3) to retain its runtime fixes. v229: two-wheel reviewed dependency delta (soupsieve 4.1.1, tornado 6.6.1); one OD1 cache-removal step.
FROM ericsonjulio/erpnext@sha256:aefceb2e19e8f100f0b1f93a1fe10019b8f3ef09d4b69e7a82dbeb2f92358e5b
USER frappe
WORKDIR /home/frappe/frappe-bench
COPY --chown=frappe:frappe v229-tools/ /tmp/upgrade-229/
RUN env/bin/python -I -B /tmp/upgrade-229/verify-dependencies.py before --verify-lock /tmp/upgrade-229/patchers/verify-python-lock.py --lock-before /tmp/upgrade-229/python-security-v228.lock --lock-after /tmp/upgrade-229/python-security-v229.lock --lock-maintenance /tmp/upgrade-229/maintenance-python-security.lock && env/bin/python -I -B /tmp/upgrade-229/verify-retained.py
RUN rm -rf apps/frappe apps/erpnext apps/hrms apps/crm apps/helpdesk apps/drive apps/eam apps/my_branding
COPY --chown=frappe:frappe apps/ apps/
RUN env/bin/python -I -B /tmp/upgrade-229/apply-source.py /home/frappe/frappe-bench --verify
# Dependency delta (recipe/deps/v229): exactly two hash-pinned wheels (soupsieve 2.9.2 -> 4.1.1, tornado 6.6 -> 6.6.1), installed offline in the SAME RUN as
# the editable apps and before the single `uv pip check`. Nothing else may change: verify-dependencies.py `after` proves the exact delta, unchanged bytes elsewhere and faithful wheel installs.
RUN UV_NO_CACHE=1 PYTHONDONTWRITEBYTECODE=1 uv pip install --python env/bin/python --no-deps --no-index --find-links /tmp/upgrade-229/wheels --require-hashes --only-binary :all: --reinstall -r /tmp/upgrade-229/python-delta-wheels.lock && UV_NO_CACHE=1 PYTHONDONTWRITEBYTECODE=1 uv pip install --python env/bin/python --no-deps --no-build-isolation --no-index -e apps/frappe -e apps/erpnext -e apps/hrms -e apps/crm -e apps/helpdesk -e apps/drive -e apps/eam -e apps/my_branding && UV_NO_CACHE=1 uv pip check --python env/bin/python
RUN env/bin/python -I -B /tmp/upgrade-229/verify-dependencies.py after --verify-lock /tmp/upgrade-229/patchers/verify-python-lock.py --lock-before /tmp/upgrade-229/python-security-v228.lock --lock-after /tmp/upgrade-229/python-security-v229.lock --lock-maintenance /tmp/upgrade-229/maintenance-python-security.lock
# Native gate: the v228 delta distributions (inherited from the base image) and the two delta wheels import on this image at exactly the reviewed versions; tornado's abi3 extension loads on 3.14; a bs4 select goes through soupsieve 4.1.1.
RUN env/bin/python -I -B -c "import plutoprint, fontTools, filelock, oauthlib, soupsieve, tornado, tornado.speedups, bs4, importlib.metadata as m; v = {n: m.version(n) for n in ('filelock', 'fonttools', 'oauthlib', 'plutoprint', 'soupsieve', 'tornado')}; assert v == {'filelock': '4.2.4', 'fonttools': '4.68.0', 'oauthlib': '4.0.1', 'plutoprint': '0.22.0', 'soupsieve': '4.1.1', 'tornado': '6.6.1'}, v; assert filelock.__version__ == v['filelock'] and fontTools.version == v['fonttools'] and oauthlib.__version__ == v['oauthlib'], (filelock.__version__, fontTools.version, oauthlib.__version__); assert filelock.FileLock.__name__ == 'UnixFileLock'; assert soupsieve.__version__ == v['soupsieve'] and tornado.version == v['tornado'], (soupsieve.__version__, tornado.version); assert [e.name for e in bs4.BeautifulSoup('<div><p class=a>x</p><p>y</p></div>', 'html.parser').select('div > p.a')] == ['p']; print(v)"
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-229/build-state/tmp TMP=/tmp/upgrade-229/build-state/tmp TEMP=/tmp/upgrade-229/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-229/build-state/yarn-cache npm_config_cache=/tmp/upgrade-229/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-229/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-229/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-229/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-229/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/frappe install --frozen-lockfile --network-timeout 300000 && yarn --cwd apps/frappe/ui install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-229/build-state/tmp TMP=/tmp/upgrade-229/build-state/tmp TEMP=/tmp/upgrade-229/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-229/build-state/yarn-cache npm_config_cache=/tmp/upgrade-229/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-229/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-229/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-229/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-229/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/erpnext install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/erpnext/banking install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-229/build-state/tmp TMP=/tmp/upgrade-229/build-state/tmp TEMP=/tmp/upgrade-229/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-229/build-state/yarn-cache npm_config_cache=/tmp/upgrade-229/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-229/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-229/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-229/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-229/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/hrms install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/hrms/frontend install --frozen-lockfile --network-timeout 300000 && yarn --cwd apps/hrms/roster install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-229/build-state/tmp TMP=/tmp/upgrade-229/build-state/tmp TEMP=/tmp/upgrade-229/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-229/build-state/yarn-cache npm_config_cache=/tmp/upgrade-229/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-229/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-229/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-229/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-229/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/crm install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/crm/frontend install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-229/build-state/tmp TMP=/tmp/upgrade-229/build-state/tmp TEMP=/tmp/upgrade-229/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-229/build-state/yarn-cache npm_config_cache=/tmp/upgrade-229/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-229/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-229/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-229/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-229/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    yarn --cwd apps/helpdesk install --frozen-lockfile --ignore-scripts --network-timeout 300000 && yarn --cwd apps/helpdesk/desk install --frozen-lockfile --network-timeout 300000
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-229/build-state/tmp TMP=/tmp/upgrade-229/build-state/tmp TEMP=/tmp/upgrade-229/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-229/build-state/yarn-cache npm_config_cache=/tmp/upgrade-229/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-229/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-229/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-229/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-229/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    test "$(pnpm --version)" = 10.34.9 && pnpm --dir apps/drive/frontend --store-dir /tmp/upgrade-229/build-state/pnpm-store install --frozen-lockfile
RUN env/bin/python -I -B /tmp/upgrade-229/patch-installed-dependencies.py /home/frappe/frappe-bench && env/bin/python -I -B /tmp/upgrade-229/patch-installed-dependencies.py /home/frappe/frappe-bench --verify
RUN env/bin/python -I -B /tmp/upgrade-229/patchers/security/apply.py --verify /home/frappe/frappe-bench
RUN test ! -e sites/assets && mkdir -p sites/assets && cp -a assets/. sites/assets/
# Preserve inherited logs and residue; every build tool uses removable private state.
# Build replaced apps only; retained apps keep their exact inherited output.
RUN set -eu; \
    export TMPDIR=/tmp/upgrade-229/build-state/tmp TMP=/tmp/upgrade-229/build-state/tmp TEMP=/tmp/upgrade-229/build-state/tmp \
        YARN_CACHE_FOLDER=/tmp/upgrade-229/build-state/yarn-cache npm_config_cache=/tmp/upgrade-229/build-state/npm-cache npm_config_store_dir=/tmp/upgrade-229/build-state/pnpm-store \
        XDG_CACHE_HOME=/tmp/upgrade-229/build-state/xdg-cache XDG_STATE_HOME=/tmp/upgrade-229/build-state/xdg-state XDG_DATA_HOME=/tmp/upgrade-229/build-state/xdg-data \
        COREPACK_HOME=/home/frappe/.cache/node/corepack COREPACK_ENABLE_NETWORK=0 COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_AUTO_PIN=0 \
        NO_UPDATE_NOTIFIER=1 npm_config_update_notifier=false YARN_DISABLE_SELF_UPDATE_CHECK=1 DISABLE_V8_COMPILE_CACHE=1 NODE_DISABLE_COMPILE_CACHE=1; \
    mkdir -p "$TMPDIR"; \
    scratch="$(mktemp -d "$TMPDIR/bench-build.XXXXXX")"; \
    test -d logs && test ! -L logs; mv logs "$scratch/original-logs"; \
    restore() { result="$?"; trap - 0; rm -rf logs; mv "$scratch/original-logs" logs; rm -rf "$scratch"; exit "$result"; }; \
    trap restore 0; mkdir logs; \
    export PYTHONDONTWRITEBYTECODE=1 UV_NO_CACHE=1; \
    for app in frappe erpnext hrms crm helpdesk; do bench build --app "$app" --production --force; if [ "$app" = crm ]; then env/bin/python -I -B /tmp/upgrade-229/patchers/crm-pulse/verify.py --verify /home/frappe/frappe-bench; fi; done; \
    yarn --cwd apps/frappe run production --apps drive; pnpm --dir apps/drive/frontend build; bench build --app drive --production --force --using-cached; \
    bench build --app eam --production --force; bench build --app my_branding --production --force; bench --version
RUN rm -rf /tmp/upgrade-229/build-state && rm -rf assets && cp -a sites/assets assets && rm -rf sites/assets
# OD1 (clean-base D7, reviewed-removals.json): drop the three dead build caches; runs as frappe, no network.
RUN rm -rf /home/frappe/.cache/yarn /home/frappe/.cache/uv /home/frappe/.local/share/pnpm/store
RUN env/bin/python -I -B /tmp/upgrade-229/apply-source.py /home/frappe/frappe-bench --verify && env/bin/python -I -B /tmp/upgrade-229/verify-dependencies.py after --verify-lock /tmp/upgrade-229/patchers/verify-python-lock.py --lock-before /tmp/upgrade-229/python-security-v228.lock --lock-after /tmp/upgrade-229/python-security-v229.lock --lock-maintenance /tmp/upgrade-229/maintenance-python-security.lock
LABEL com.nexumair.release="v16-prod-229" com.nexumair.framework.release="v16-prod-229" \
      com.nexumair.frappe.version="16.56.0" com.nexumair.erpnext.version="16.55.0" \
      com.nexumair.base.digest="sha256:aefceb2e19e8f100f0b1f93a1fe10019b8f3ef09d4b69e7a82dbeb2f92358e5b" \
      com.nexumair.my_branding.source="v16-prod-229" com.nexumair.branding.commit="8cf99edd4da1a666f74de1f1cccedaf9533d2527" \
      com.nexumair.my_branding.commit="8cf99edd4da1a666f74de1f1cccedaf9533d2527" com.nexumair.eam.commit="97ebff6032d6f39500149233771e32377c31df6c" \
      com.nexumair.my_branding_sha="8cf99ed" com.nexumair.eam_sha="97ebff6"

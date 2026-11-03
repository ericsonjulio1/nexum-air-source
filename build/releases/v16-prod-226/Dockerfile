# Derived app-only release. All dependency/security changes are inherited from this exact base.
FROM ericsonjulio/erpnext@sha256:aceff94d1931577fb00aede83a6663297bb44cd92959e922b605bdf45388c3e7
USER frappe
WORKDIR /home/frappe/frappe-bench
ENV NODE_OPTIONS="--max-old-space-size=2560 --use-openssl-ca"
RUN rm -rf apps/eam apps/my_branding
COPY --chown=frappe:frappe eam/ apps/eam/
COPY --chown=frappe:frappe my_branding/ apps/my_branding/
RUN test ! -e apps/my_branding/my_branding/fixtures/workspace.json && test -f apps/my_branding/my_branding/seed/settings_workspace_v1.json
RUN env/bin/python -I -B -c "import ast,pathlib,tomllib; [ast.parse(p.read_bytes(),filename=str(p)) for a in ('eam','my_branding') for p in pathlib.Path('apps',a).rglob('*.py')]; assert all(tomllib.loads(pathlib.Path('apps',a,'pyproject.toml').read_text())['project']['dependencies']==[] for a in ('eam','my_branding'))"
RUN env/bin/python -I -B -c "import importlib.metadata as m,importlib.util as u,json,pathlib; [None for a in ('eam','my_branding') if (pathlib.Path(u.find_spec(a).origin).resolve().is_relative_to(pathlib.Path('apps',a).resolve()) and json.loads(m.distribution(a).read_text('direct_url.json'))['dir_info']['editable']) or (_ for _ in ()).throw(RuntimeError('editable app drift: '+a))]"
# Keep the v225 asset recipe; no resolver, Yarn install or upstream frontend rebuild.
RUN test ! -e sites/assets && mkdir -p sites/assets && cp -a assets/. sites/assets/
RUN PYTHONDONTWRITEBYTECODE=1 bench build --app eam --production --force
RUN PYTHONDONTWRITEBYTECODE=1 bench build --app my_branding --production --force
RUN rm -rf assets && cp -a sites/assets assets && rm -rf sites/assets
RUN env/bin/python -I -B /tmp/upgrade-225/verify-python-lock.py /tmp/upgrade-225/python-security.lock && uv pip check --python env/bin/python
RUN /usr/local/bin/python -I -B /tmp/upgrade-225/verify-python-lock.py /tmp/upgrade-225/maintenance-python-security.lock --maintenance && uv pip check --python /usr/local/bin/python && PYTHONDONTWRITEBYTECODE=1 bench --version
LABEL com.nexumair.release="v16-prod-226" \
      com.nexumair.base.digest="sha256:aceff94d1931577fb00aede83a6663297bb44cd92959e922b605bdf45388c3e7" \
      com.nexumair.my_branding.source="v16-prod-226" \
      com.nexumair.branding.commit="d45d82c0cc3092dcaa5ced95b4f7eeae4a470d63" \
      com.nexumair.my_branding.commit="d45d82c0cc3092dcaa5ced95b4f7eeae4a470d63" \
      com.nexumair.my_branding_sha="d45d82c" \
      com.nexumair.eam.commit="da5720a43ef8e8d7971ac4ba6e3c417760c345bc" \
      com.nexumair.eam_sha="da5720a"

FROM ericsonjulio/erpnext@sha256:a601fe57c981461d2c4c4d29d6a2bc2bd81b5c22d7d49d5a2ff6cb005aba5a41
USER frappe
WORKDIR /home/frappe/frappe-bench
RUN rm -rf apps/my_branding apps/eam
COPY --chown=frappe:frappe my_branding/ apps/my_branding/
COPY --chown=frappe:frappe eam/ apps/eam/
RUN env/bin/python -B -c "import ast,pathlib; [ast.parse(p.read_text()) for app in ('my_branding','eam') for p in pathlib.Path('apps',app).rglob('*.py')]"
LABEL com.nexumair.release="v16-prod-221" \
      com.nexumair.my_branding.commit="d3aab28c735ad0d42fcc0b01104af3b8ec20a1aa" \
      com.nexumair.branding.commit="d3aab28c735ad0d42fcc0b01104af3b8ec20a1aa" \
      com.nexumair.my_branding_sha="d3aab28" \
      com.nexumair.my_branding.source="v16-prod-221" \
      com.nexumair.eam.commit="50725b23392fd42aab0947eafe2d765e7331d0f0" \
      com.nexumair.eam_sha="50725b2"

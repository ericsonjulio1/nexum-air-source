FROM ericsonjulio/erpnext@sha256:cd7885c811f256bcb5f25409dd475323e047e0cf1761246a8e72eccaea1dbe65
USER frappe
WORKDIR /home/frappe/frappe-bench
RUN rm -rf apps/my_branding apps/eam
COPY --chown=frappe:frappe my_branding/ apps/my_branding/
COPY --chown=frappe:frappe eam/ apps/eam/
RUN env/bin/python -B -c "import ast,pathlib; [ast.parse(p.read_text()) for app in ('my_branding','eam') for p in pathlib.Path('apps',app).rglob('*.py')]"
LABEL com.nexumair.release="v16-prod-223" \
      com.nexumair.my_branding.commit="e734e49d054b611bd66e1178d75b58a8c8a5a415" \
      com.nexumair.branding.commit="e734e49d054b611bd66e1178d75b58a8c8a5a415" \
      com.nexumair.my_branding_sha="e734e49" \
      com.nexumair.my_branding.source="v16-prod-223" \
      com.nexumair.eam.commit="9de5ada9a7e57e5fb3db91f02bb93c7c67a81881" \
      com.nexumair.eam_sha="9de5ada"

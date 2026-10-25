FROM ericsonjulio/erpnext@sha256:c229566a95fcce23c7843ccfb5115ccaed6bc34322522c848fa0cefc8b25c919
USER frappe
WORKDIR /home/frappe/frappe-bench
RUN rm -rf apps/my_branding apps/eam
COPY --chown=frappe:frappe my_branding/ apps/my_branding/
COPY --chown=frappe:frappe eam/ apps/eam/
RUN env/bin/python -B -c "import ast,pathlib; [ast.parse(p.read_text()) for app in ('my_branding','eam') for p in pathlib.Path('apps',app).rglob('*.py')]"
LABEL com.nexumair.release="v16-prod-224" \
      com.nexumair.my_branding.commit="206eb4b4835de66507459c9f8296e898bc22bc86" \
      com.nexumair.branding.commit="206eb4b4835de66507459c9f8296e898bc22bc86" \
      com.nexumair.my_branding_sha="206eb4b" \
      com.nexumair.my_branding.source="v16-prod-224" \
      com.nexumair.eam.commit="9de5ada9a7e57e5fb3db91f02bb93c7c67a81881" \
      com.nexumair.eam_sha="9de5ada"

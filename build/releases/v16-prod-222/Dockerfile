FROM ericsonjulio/erpnext@sha256:d74ea06d183b20a80292028670ae2fd0db76edd14bab6b3491137bc2d3cc7acb
USER frappe
WORKDIR /home/frappe/frappe-bench
RUN rm -rf apps/my_branding apps/eam
COPY --chown=frappe:frappe my_branding/ apps/my_branding/
COPY --chown=frappe:frappe eam/ apps/eam/
RUN env/bin/python -B -c "import ast,pathlib; [ast.parse(p.read_text()) for app in ('my_branding','eam') for p in pathlib.Path('apps',app).rglob('*.py')]"
LABEL com.nexumair.release="v16-prod-222" \
      com.nexumair.my_branding.commit="8c52989cd390df462c94b0e4dd40a2eca698bfcc" \
      com.nexumair.branding.commit="8c52989cd390df462c94b0e4dd40a2eca698bfcc" \
      com.nexumair.my_branding_sha="8c52989" \
      com.nexumair.my_branding.source="v16-prod-222" \
      com.nexumair.eam.commit="9de5ada9a7e57e5fb3db91f02bb93c7c67a81881" \
      com.nexumair.eam_sha="9de5ada"

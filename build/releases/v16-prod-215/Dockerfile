FROM ericsonjulio/erpnext@sha256:80c646bb6638280a00e0d061f5ffcb4b3f884fb2ab095abd49e536ff54db5787
USER root
# Replace complete custom source trees, including removals; keep inherited
# Python dependencies and the pinned upstream applications unchanged.
RUN rm -rf /home/frappe/frappe-bench/apps/my_branding /home/frappe/frappe-bench/apps/eam
COPY --chown=frappe:frappe my_branding/ /home/frappe/frappe-bench/apps/my_branding/
COPY --chown=frappe:frappe eam/ /home/frappe/frappe-bench/apps/eam/
USER frappe
LABEL com.nexumair.release="v16-prod-215" com.nexumair.branding.commit="068907ca7908074c2416961aa2470ee5939d2922" com.nexumair.eam.commit="1006c2dfb9a1e40271d0823a9944598ce105ba84"

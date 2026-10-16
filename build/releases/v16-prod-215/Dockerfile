FROM ericsonjulio/erpnext@sha256:80c646bb6638280a00e0d061f5ffcb4b3f884fb2ab095abd49e536ff54db5787
USER root
# Replace complete custom source trees, including removals; keep inherited
# Python dependencies and the pinned upstream applications unchanged.
RUN rm -rf /home/frappe/frappe-bench/apps/my_branding /home/frappe/frappe-bench/apps/eam
COPY --chown=frappe:frappe my_branding/ /home/frappe/frappe-bench/apps/my_branding/
COPY --chown=frappe:frappe eam/ /home/frappe/frappe-bench/apps/eam/
USER frappe
LABEL com.nexumair.release="v16-prod-215" com.nexumair.branding.commit="PENDING" com.nexumair.eam.commit="PENDING"

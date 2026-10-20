FROM ericsonjulio/erpnext@sha256:23dad475de3ed661317dd5ac2ad3edd8c4d59539238f22296c82314ab1468468
USER root
# Replace the complete my_branding source tree, including removals; eam, the
# pinned upstream applications and their Python dependencies stay v216's.
RUN rm -rf /home/frappe/frappe-bench/apps/my_branding
COPY --chown=frappe:frappe my_branding/ /home/frappe/frappe-bench/apps/my_branding/
USER frappe
LABEL com.nexumair.release="v16-prod-217" com.nexumair.branding.commit="8fd8cc3dd63c3110a12889baa448799722138dff" com.nexumair.eam.commit="05c867e650eadb181cf379ac88a75c555a1d2c0f"

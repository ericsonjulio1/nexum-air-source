FROM ericsonjulio/erpnext@sha256:3fda4eb33b4341819da28ac153b9ea4da171b11ad38fec01079967a594ff8238
USER root
# Replace the complete my_branding source tree, including removals; eam, the
# pinned upstream applications and their Python dependencies stay v216's.
RUN rm -rf /home/frappe/frappe-bench/apps/my_branding
COPY --chown=frappe:frappe my_branding/ /home/frappe/frappe-bench/apps/my_branding/
USER frappe
LABEL com.nexumair.release="v16-prod-219" com.nexumair.branding.commit="16fae11ed4ba5a6e90f10b9c7ba533688ae35012" com.nexumair.eam.commit="05c867e650eadb181cf379ac88a75c555a1d2c0f"

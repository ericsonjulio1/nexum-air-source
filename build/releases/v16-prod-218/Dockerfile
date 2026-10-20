FROM ericsonjulio/erpnext@sha256:8d6044e034080ca6ab53b00a91bd8b67c2231414d631ac075ac1cc3dd318492c
USER root
# Replace the complete my_branding source tree, including removals; eam, the
# pinned upstream applications and their Python dependencies stay v216's.
RUN rm -rf /home/frappe/frappe-bench/apps/my_branding
COPY --chown=frappe:frappe my_branding/ /home/frappe/frappe-bench/apps/my_branding/
USER frappe
LABEL com.nexumair.release="v16-prod-218" com.nexumair.branding.commit="636bb1a56ed89901722f3771c6324ef13db6efe7" com.nexumair.eam.commit="05c867e650eadb181cf379ac88a75c555a1d2c0f"

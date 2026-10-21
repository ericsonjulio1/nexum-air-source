FROM ericsonjulio/erpnext@sha256:8a344bf75b77639e897a7a058711f594089586b58dec34fc004c76a75b98b748
USER root
# Replace only the complete private eam source tree, including removals;
# my_branding, upstream applications and dependencies stay v219's.
RUN rm -rf /home/frappe/frappe-bench/apps/eam
COPY --chown=frappe:frappe eam/ /home/frappe/frappe-bench/apps/eam/
USER frappe
LABEL com.nexumair.release="v16-prod-220" com.nexumair.branding.commit="16fae11ed4ba5a6e90f10b9c7ba533688ae35012" com.nexumair.eam.commit="f806e3d7ccaea10f31b0d4bc8a91aa8d5cb7df5d"

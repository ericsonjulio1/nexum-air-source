FROM ericsonjulio/erpnext@sha256:0ddb340dc9cee825f4fe75011d45748267873a79c9d20fc317dd5057e17071f8
USER root
COPY --chown=frappe:frappe my_branding/ /home/frappe/frappe-bench/apps/my_branding/
COPY --chown=frappe:frappe eam/ /home/frappe/frappe-bench/apps/eam/
USER frappe
LABEL com.nexumair.release="v16-prod-213" com.nexumair.branding.commit="97b677c946ed69e6c20a88051a6b9f45f6da1f97" com.nexumair.eam.commit="a2ea3f76cb34005b98b880b2c2a10c85a041ea4a"

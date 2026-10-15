FROM ericsonjulio/erpnext@sha256:dd0411853c61fe1b210974ced5257ffb1bd26df08d3dfb14b8be50b298e5f11f
USER root
COPY --chown=frappe:frappe my_branding/ /home/frappe/frappe-bench/apps/my_branding/
COPY --chown=frappe:frappe eam/ /home/frappe/frappe-bench/apps/eam/
USER frappe

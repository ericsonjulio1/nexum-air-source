FROM ericsonjulio/erpnext@sha256:dbfe240dec4283e6d283769b5201073f8f9784b1deb43bc4877ce9dbcbb574a6
USER root
COPY --chown=frappe:frappe my_branding/ /home/frappe/frappe-bench/apps/my_branding/
COPY --chown=frappe:frappe eam/ /home/frappe/frappe-bench/apps/eam/
USER frappe

FROM ericsonjulio/erpnext@sha256:cee70d462adf59b1d460e67f72cffb867142d63a59d873d64e1959ab5a07c292
USER root
COPY --chown=frappe:frappe apply_frontend.py /tmp/suite209/apply_frontend.py
USER frappe
RUN env/bin/python /tmp/suite209/apply_frontend.py /home/frappe/frappe-bench
RUN mkdir -p sites/assets && cp -a assets/. sites/assets/
RUN bench build --apps crm,helpdesk,insights --production --force
RUN rm -rf assets && cp -a sites/assets assets && rm -rf sites/assets
USER root
COPY --chown=frappe:frappe my_branding/ /home/frappe/frappe-bench/apps/my_branding/
COPY --chown=frappe:frappe eam/ /home/frappe/frappe-bench/apps/eam/
USER frappe
LABEL com.nexumair.release="v16-prod-209" com.nexumair.branding.commit="2d045ffaf40b4c5fae450d24f29371e06f079a28" com.nexumair.eam.commit="07717b9c85413229ac33c8e963f83d536ca894b8"

FROM ericsonjulio/erpnext@sha256:ef631ac885c5d46485569ee2d5b9d2a04cd28d5047bfde81d4b85354d135dd12
USER root
COPY --chown=frappe:frappe apply_frontend.py TeamsUserDropdown.vue /tmp/navigation210/
USER frappe
RUN env/bin/python /tmp/navigation210/apply_frontend.py /home/frappe/frappe-bench
# Reuse exact dependencies from the pinned image; root Drive build would reinstall them.
RUN cd apps/drive/frontend && yarn build && cd ../../gameplan/frontend && yarn build
USER root
COPY --chown=frappe:frappe my_branding/ /home/frappe/frappe-bench/apps/my_branding/
COPY --chown=frappe:frappe eam/ /home/frappe/frappe-bench/apps/eam/
USER frappe
LABEL com.nexumair.release="v16-prod-210" com.nexumair.branding.commit="f593f52b2e3ebe63f4be092eed5d6356d370144c" com.nexumair.eam.commit="905c47d3e091d7d8ff1597f68572e5f811e7b6f6"

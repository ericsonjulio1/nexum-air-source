FROM ericsonjulio/erpnext@sha256:beb3f9f1c8e8f1f195486ae0036836b8dabc564a84b3742d1e9aa2e017094ddf AS frontend
USER root
COPY --chown=frappe:frappe apply_frontend.py /tmp/native214/apply_frontend.py
USER frappe
RUN env/bin/python /tmp/native214/apply_frontend.py /home/frappe/frappe-bench
# Build from pinned sources and their inherited dependencies; no package updates.
RUN cd apps/crm/frontend && yarn build
RUN cd apps/helpdesk/desk && yarn build
RUN cd apps/insights/frontend && yarn build
RUN cd apps/drive/frontend && yarn build
RUN cd apps/gameplan/frontend && yarn build
RUN cd apps/hrms/roster && yarn build

FROM frontend
USER root
COPY --chown=frappe:frappe my_branding/ /home/frappe/frappe-bench/apps/my_branding/
COPY --chown=frappe:frappe eam/ /home/frappe/frappe-bench/apps/eam/
USER frappe
LABEL com.nexumair.release="v16-prod-214" com.nexumair.branding.commit="e0e132a2f9911b7ed5b2f42b6b67acdb1b501e2c" com.nexumair.eam.commit="da0fcc1074044060ca60746aac7718c4150ffb0e"

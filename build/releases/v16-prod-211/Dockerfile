FROM ericsonjulio/erpnext@sha256:87c0424fa58040f336a008826e7a8b8a88412fe546cee76baf68fd3d81cf855f
USER root
COPY --chown=frappe:frappe apply_runtime.py lifecycle.test.cjs /tmp/performance211/
USER frappe
RUN env/bin/python /tmp/performance211/apply_runtime.py /home/frappe/frappe-bench \
    && BENCH_ROOT=/home/frappe/frappe-bench node --test /tmp/performance211/lifecycle.test.cjs
# Rebuild only affected frontends with the exact dependencies inherited from v210.
RUN cd apps/gameplan/frontend && yarn build
RUN mkdir -p sites/assets && cp -a assets/. sites/assets/
RUN bench build --app frappe --production --force
RUN rm -rf assets && cp -a sites/assets assets && rm -rf sites/assets
USER root
COPY --chown=frappe:frappe my_branding/ /home/frappe/frappe-bench/apps/my_branding/
COPY --chown=frappe:frappe eam/ /home/frappe/frappe-bench/apps/eam/
USER frappe
LABEL com.nexumair.release="v16-prod-211" com.nexumair.branding.commit="1aa01cc24c98f6708718cd49b71ad0ed6bad4a48" com.nexumair.eam.commit="905c47d3e091d7d8ff1597f68572e5f811e7b6f6"

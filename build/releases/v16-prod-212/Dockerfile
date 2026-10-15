FROM ericsonjulio/erpnext@sha256:736e4cb0c03bd7291290805efebd908881841a17e0778b59e9c14f442c22fdfe
USER root
COPY --chown=frappe:frappe apply_runtime.py empty_chart.test.cjs /tmp/performance212/
USER frappe
RUN env/bin/python /tmp/performance212/apply_runtime.py /home/frappe/frappe-bench \
    && BENCH_ROOT=/home/frappe/frappe-bench node --test /tmp/performance212/empty_chart.test.cjs
RUN mkdir -p sites/assets && cp -a assets/. sites/assets/
RUN bench build --app frappe --production --force
RUN rm -rf assets && cp -a sites/assets assets && rm -rf sites/assets
LABEL com.nexumair.release="v16-prod-212"

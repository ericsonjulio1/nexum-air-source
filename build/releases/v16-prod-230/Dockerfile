# App-only reproduction of v16-prod-230 on the exact v229 image. This is NOT the file that built
# the deployed image: that build re-ran the v229 recipe on this base (see README.md). Every
# upstream source, overlay and dependency input was byte-identical to v229, so this file replaces
# only the two changed custom applications and rebuilds only their frontend assets.
FROM ericsonjulio/erpnext@sha256:fe553f13107d4209c8c6d157f3fc3a203e7f535eb4a901e6db795bf90e5ecbaa
USER frappe
WORKDIR /home/frappe/frappe-bench
RUN rm -rf apps/eam apps/my_branding
COPY --chown=frappe:frappe eam/ apps/eam/
COPY --chown=frappe:frappe my_branding/ apps/my_branding/
# The deployed build reinstalled its replaced apps the same way (no index, no dependencies).
RUN UV_NO_CACHE=1 PYTHONDONTWRITEBYTECODE=1 uv pip install --python env/bin/python --no-deps --no-build-isolation --no-index -e apps/eam -e apps/my_branding && UV_NO_CACHE=1 uv pip check --python env/bin/python
RUN test ! -e sites/assets && mkdir -p sites/assets && cp -a assets/. sites/assets/
RUN PYTHONDONTWRITEBYTECODE=1 UV_NO_CACHE=1 bench build --app eam --production --force
RUN PYTHONDONTWRITEBYTECODE=1 UV_NO_CACHE=1 bench build --app my_branding --production --force
RUN rm -rf assets && cp -a sites/assets assets && rm -rf sites/assets
# The v229 tools in the base re-verify the 49 retained source overlays and the dependency set.
RUN env/bin/python -I -B /tmp/upgrade-229/apply-source.py /home/frappe/frappe-bench --verify && env/bin/python -I -B /tmp/upgrade-229/verify-dependencies.py after --verify-lock /tmp/upgrade-229/patchers/verify-python-lock.py --lock-before /tmp/upgrade-229/python-security-v228.lock --lock-after /tmp/upgrade-229/python-security-v229.lock --lock-maintenance /tmp/upgrade-229/maintenance-python-security.lock
LABEL com.nexumair.release="v16-prod-230" com.nexumair.framework.release="v16-prod-230" \
      com.nexumair.frappe.version="16.56.0" com.nexumair.erpnext.version="16.55.0" \
      com.nexumair.base.digest="sha256:fe553f13107d4209c8c6d157f3fc3a203e7f535eb4a901e6db795bf90e5ecbaa" \
      com.nexumair.my_branding.source="v16-prod-230" com.nexumair.branding.commit="9e8925c6a2bac45fc200c06cab0e12ad23b69fb9" \
      com.nexumair.my_branding.commit="9e8925c6a2bac45fc200c06cab0e12ad23b69fb9" com.nexumair.eam.commit="339920ce7dd63c774a2ee2eb6d25de137701b6a3" \
      com.nexumair.my_branding_sha="9e8925c" com.nexumair.eam_sha="339920c"

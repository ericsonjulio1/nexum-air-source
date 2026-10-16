# v16-prod-215

This release reduces the complete animated login chip and plant by approximately 58% from the original, leaving more space around the assembly while preserving its motion and wordmark. The final framing is another 29% smaller than the initial review candidate. Encoded videos reduce transfer size by approximately 66–67%.

Custom-app fixes cover maintenance cancellation provenance, negative consumption validation, report source permissions, native invoice tax/rounding presentation, zero-rate tax overrides, atomic chart reconciliation, setup completion, Workbench request/query overhead and shared theme synchronization.

The immutable v214 base retains the exact upstream framework, security fixes and compiled SPA bundles. The two complete custom-app Git archives replace their prior image directories; dependencies are not upgraded. No historical full-build patcher is run by this overlay. The historical Growth patcher is separately hardened for older-source reproducibility.

Run `prepare.py --branding /path/to/my_branding --eam /path/to/eam` after the manifest and Dockerfile contain final reviewed commits, then build this directory for `linux/amd64`. All guards remain active under Python optimization. Generated archives are ignored by Git. The manifest records the accepted registry digest.

Release gates include native accounting/maintenance regressions, exact scenario VAT/withholding/depreciation assertions, native Balance Sheet/Trial Balance reconciliation, first/repeated migration parity, browser/Mac regressions and fresh production backups. The final candidate is independently reviewed with Claude Opus 5.5; only actual credit exhaustion permits the owner's authorized local assessment fallback. Evidence and residual limitations are recorded privately without publishing credentials or business data.

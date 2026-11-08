// Same-origin inert stand-in for the frappe-ui Pulse client (import-map target set by
// my_branding.spa_brand). No telemetry initialization, no network, no side effects.
export class PulseClient {
  constructor(opts) {}
  async init() { return false; }
  stop() {}
  capture() {}
  getDistinctId() { return ''; }
}

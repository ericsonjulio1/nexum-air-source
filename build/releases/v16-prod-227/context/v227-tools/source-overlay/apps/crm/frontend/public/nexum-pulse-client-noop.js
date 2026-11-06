// CRM-only import-map target. No telemetry initialization or side effects.
export class PulseClient {
  constructor(opts) {}
  async init() { return false; }
  stop() {}
  capture() {}
  getDistinctId() { return ''; }
}

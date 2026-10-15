"""Lifecycle fixes for the exact v210 runtime; fail before editing on source drift."""
from pathlib import Path
import hashlib
import sys

HASHES = {
    'apps/gameplan/frontend/node_modules/frappe-ui/src/resources/listResource.js': '5ab122a679f9afee8073e4eba9e7eba756d58e7382cebd685a16362ca1eb725a',
    'apps/gameplan/frontend/node_modules/frappe-ui/src/resources/plugin.js': '1be5cf7b4a368ca8efb9ec3d3d15d508df1011c333c146e9ffdf4087ba4505a8',
    'apps/gameplan/frontend/node_modules/frappe-ui/src/resources/realtime.js': '85921ccb9e2aa8ea72fc8b3436bfec87780d4259ffc477f268f911f0945a6b96',
    'apps/gameplan/frontend/src/components/DiscussionList.vue': '58f19f6f16391da614ad43607d7dbaf2a58f4f53b5ec96c3bd95024661f82e2e',
    'apps/frappe/frappe/public/js/frappe/widgets/chart_widget.js': 'e1ccecbb47cf1c54819ce5c601e72892caca1e20ea5ab6751502ce0405809c8e',
}


def apply(root):
    originals = {name: (root / name).read_bytes() for name in HASHES}
    for name, expected in HASHES.items():
        if hashlib.sha256(originals[name]).hexdigest() != expected:
            raise ValueError(f'Unexpected v210 source: {name}')
    patched = {name: value.decode() for name, value in originals.items()}

    def replace(name, old, new, count=1):
        assert patched[name].count(old) == count, (name, old, patched[name].count(old))
        patched[name] = patched[name].replace(old, new)

    resource, plugin, realtime, discussions, chart = HASHES
    replace(resource, '  let out = reactive({', '''  let disposed = false
  let stopRealtime
  let out = reactive({''')
    replace(resource, '    getRow,\n', '    getRow,\n    dispose,\n')
    replace(resource, '  function update(updatedOptions) {', '''  // Cached lists are shared and must survive a single consumer unmounting.
  // Uncached lists belong to the component that created them.
  function dispose() {
    if (cacheKey || disposed) return
    disposed = true
    stopRealtime?.()
    const resources = resourcesByDocType[out.doctype] || []
    const index = resources.indexOf(out)
    if (index !== -1) resources.splice(index, 1)
    if (!resources.length) delete resourcesByDocType[out.doctype]
  }

  function update(updatedOptions) {''')
    replace(resource, '    onDocUpdate(vm.$socket, out.doctype, (name) => {',
            '    stopRealtime = onDocUpdate(vm.$socket, out.doctype, (name) => {')
    replace(plugin, '''              if (!options) {
                return
              }''', '''              if (!options) {
                this._resources[key]?.dispose?.()
                delete this._resources[key]
                return
              }''')
    replace(plugin, '''              if (!changed) return
              this._resources[key]''', '''              if (!changed) return
              this._resources[key]?.dispose?.()
              this._resources[key]''')
    replace(plugin, '  methods: {', '''  beforeUnmount() {
    for (const resource of Object.values(this._resources || {})) {
      resource.dispose?.()
    }
  },
  methods: {''')
    replace(realtime, '''  socket.on('list_update', (data) => {
    if (data.doctype == doctype) {
      callback(data.name)
    }
  })''', '''  const handler = (data) => {
    if (data.doctype == doctype) {
      callback(data.name)
    }
  }
  socket.on('list_update', handler)
  // The doctype subscription is shared; remove only this consumer's handler.
  return () => socket.off('list_update', handler)''')
    replace(discussions, "  expose: ['discussions'],", """  data() {
    return { hasActivated: false }
  },
  expose: ['discussions'],""")
    replace(discussions, '''  activated() {
    this.$resources.discussions.reload()
  },''', '''  activated() {
    // auto fetch (including cache reuse) owns the first activation. A kept-alive
    // tab still refreshes when revisited, unless that same list is fetching.
    if (this.hasActivated && !this.$resources.discussions.list.loading) {
      this.$resources.discussions.reload()
    }
    this.hasActivated = true
  },''')
    replace(chart, 'delete this.dashboard_chart;', 'this.destroy_chart();', count=4)
    replace(chart, '\trefresh() {', '''\tdestroy_chart() {
\t\tconst chart = this.dashboard_chart;
\t\tdelete this.dashboard_chart;
\t\tchart?.destroy?.();
\t}

\tdelete(...args) {
\t\tthis.deleted = true;
\t\tthis.destroy_chart();
\t\treturn super.delete(...args);
\t}

\trefresh() {''')
    replace(chart, '\tsetup_container() {\n\t\tthis.body.empty();',
            '\tsetup_container() {\n\t\tthis.destroy_chart();\n\t\tthis.body.empty();')
    replace(chart, '\t\tthis.get_settings().then(() => {',
            '\t\tthis.get_settings().then(() => {\n\t\t\tif (this.deleted) return;')
    replace(chart, '\t\tlet setup_dashboard_chart = () => {',
            '\t\tlet setup_dashboard_chart = () => {\n\t\t\tif (this.deleted) return;')
    replace(chart, '''\t\t\t\tthis.chart_wrapper.empty();
\t\t\t\tthis.destroy_chart();''', '''\t\t\t\tthis.destroy_chart();
\t\t\t\tthis.chart_wrapper.empty();''')

    for name, value in patched.items():
        (root / name).write_text(value)
    print('Applied v211: Teams resource disposal, single initial fetch, chart destruction')


if __name__ == '__main__':
    apply(Path(sys.argv[1]))

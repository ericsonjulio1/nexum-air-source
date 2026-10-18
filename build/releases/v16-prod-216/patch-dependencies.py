"""Preserve the v215 chart presentation and dependency lifecycle corrections."""
import hashlib
from pathlib import Path
import sys

root = Path(sys.argv[1])
prepared = {}
for frontend in ['crm/frontend', 'helpdesk/desk', 'insights/frontend']:
    path = root / 'apps' / frontend / 'node_modules/echarts/lib/core/echarts.js'
    text = path.read_text()
    anchor = '  ECharts.prototype.setOption = function (option, notMerge, lazyUpdate) {'
    if text.count(anchor) != 1 or 'window.NexumCharts' in text:
        raise RuntimeError('Review ECharts upstream drift: ' + str(path))
    prepared[path] = text.replace(anchor, anchor + '''
    // Nexum Air: shared presentation before ECharts consumes the original data.
    if (typeof window !== 'undefined' && window.NexumCharts) {
      option = window.NexumCharts.echartsOptions(option, this);
    }''')

components = root / 'apps/frappe/node_modules/frappe-charts/src/js/objects/ChartComponents.js'
if hashlib.sha256(components.read_bytes()).hexdigest() != 'ca7108208b4b1af81dadbe14afa4cdb0306f73ba85f0af7c8c0e2a43e1ecaeb9':
    raise RuntimeError('Review native chart dependency source drift')
text = components.read_text()
anchor = '\tlet config = componentConfigs[keys[0]];'
if text.count(anchor) != 1:
    raise RuntimeError('Native chart component anchor changed')
prepared[components] = text.replace(anchor, '\tlet config = { ...componentConfigs[keys[0]] };')
dist_hashes = {
    'frappe-charts.esm.js': ('3f4804ada1cf0a08685fd174d7335b3d186a5ba11c47f34461c40699359f9366', 'Ct'),
    'frappe-charts.umd.js': ('fc63f108c6926efd5458d27baa5bb03372a420f905795c9098cc8ce1436302eb', 'Ct'),
    'frappe-charts.cjs.js': ('6f29ae86ce0c5d7137b64512746936502382947a4ef46c0dbfe0174600d55fab', 'Tt'),
}
for name, (digest, defaults) in dist_hashes.items():
    path = components.parents[3] / 'dist' / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError('Review native chart dependency entrypoint drift: ' + name)
    text = path.read_text()
    before = f'a={defaults}[i[0]];return Object.assign(a,{{constants:e,getData:n}})'
    after = f'a=Object.assign({{}},{defaults}[i[0]]);return Object.assign(a,{{constants:e,getData:n}})'
    if text.count(before) != 1:
        raise RuntimeError('Native chart dependency entrypoint anchor changed: ' + name)
    prepared[path] = text.replace(before, after)
for path, text in prepared.items():
    path.write_text(text)
print('Preserved chart presentation and instance-owned native chart callbacks in', len(prepared), 'dependency files')

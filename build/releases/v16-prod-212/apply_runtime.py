"""Finish chart ownership for empty-state placeholders on pinned v211."""
from pathlib import Path
import hashlib
import sys

root = Path(sys.argv[1])
path = root / 'apps/frappe/frappe/public/js/frappe/widgets/chart_widget.js'
text = path.read_text()
assert hashlib.sha256(path.read_bytes()).hexdigest() == '7b985120bd9bdd373abc508282848cdc0b227b2d70ca781e887e3018e4e77f04', 'Unexpected v211 ChartWidget source'
components = root / 'apps/frappe/node_modules/frappe-charts/src/js/objects/ChartComponents.js'
component_text = components.read_text()
assert hashlib.sha256(components.read_bytes()).hexdigest() == 'ca7108208b4b1af81dadbe14afa4cdb0306f73ba85f0af7c8c0e2a43e1ecaeb9', 'Unexpected native chart component source'
dist_hashes = {
    'frappe-charts.esm.js': ('3f4804ada1cf0a08685fd174d7335b3d186a5ba11c47f34461c40699359f9366', 'Ct'),
    'frappe-charts.umd.js': ('fc63f108c6926efd5458d27baa5bb03372a420f905795c9098cc8ce1436302eb', 'Ct'),
    'frappe-charts.cjs.js': ('6f29ae86ce0c5d7137b64512746936502382947a4ef46c0dbfe0174600d55fab', 'Tt'),
}
# The npm package ships prebuilt entrypoints, which Framework imports. Apply
# the identical one-line source fix there before rebuilding Framework's bundles.
dist_patches = {}
for filename, (expected, defaults) in dist_hashes.items():
    dist_path = components.parents[3] / 'dist' / filename
    data = dist_path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected, f'Unexpected chart entrypoint: {filename}'
    old = f'a={defaults}[i[0]];return Object.assign(a,{{constants:e,getData:n}})'
    new = f'a=Object.assign({{}},{defaults}[i[0]]);return Object.assign(a,{{constants:e,getData:n}})'
    dist_text = data.decode()
    assert dist_text.count(old) == 1
    dist_patches[dist_path] = dist_text.replace(old, new)

def replace(old, new):
    global text
    assert text.count(old) == 1, (old, text.count(old))
    text = text.replace(old, new)

replace('\tdestroy_chart() {', '\tdestroy_empty_chart() {\n\t\tconst chart = this.empty_chart;\n\t\tdelete this.empty_chart;\n\t\tchart?.destroy?.();\n\t}\n\n\tdestroy_chart() {')
replace('\t\tdelete this.dashboard_chart;\n\t\tchart?.destroy?.();', '\t\tdelete this.dashboard_chart;\n\t\tchart?.destroy?.();\n\t\tthis.destroy_empty_chart();')
replace('\tshow_empty_state() {', '\tshow_empty_state() {\n\t\tthis.destroy_empty_chart();')
replace('\tasync render() {', '\tasync render() {\n\t\tif (this.deleted) return;')
replace('\t\t\tfrappe.utils.make_chart($sample[0], {', '\t\t\tthis.empty_chart = frappe.utils.make_chart($sample[0], {')
replace('\t\t} else {\n\t\t\tthis.loading.hide();\n\t\t\tthis.empty.hide();', '\t\t} else {\n\t\t\tthis.destroy_empty_chart();\n\t\t\tthis.loading.hide();\n\t\t\tthis.empty.hide();')
old = '\tlet config = componentConfigs[keys[0]];'
assert component_text.count(old) == 1
# Each instance owns its bound callback; shared defaults must never retain it.
component_text = component_text.replace(old, '\tlet config = { ...componentConfigs[keys[0]] };')
path.write_text(text)
components.write_text(component_text)
for dist_path, dist_text in dist_patches.items():
    dist_path.write_text(dist_text)
print('Applied v212: empty-state lifecycle and isolated native chart component defaults')

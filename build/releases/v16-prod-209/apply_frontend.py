"""Apply small, fail-closed source adapters to the pinned v208 frontend sources.

Rebuild the three frontends afterwards. No minified-bundle editing. This file is
part of Corresponding Source, including the ECharts dependency modification.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1])


def replace(relative, old, new, count=1):
    path = root / relative
    content = path.read_text()
    assert content.count(old) == count, (relative, content.count(old), count)
    path.write_text(content.replace(old, new))


for frontend in ['crm/frontend', 'helpdesk/desk', 'insights/frontend']:
    replace(f'apps/{frontend}/node_modules/echarts/lib/core/echarts.js',
            '  ECharts.prototype.setOption = function (option, notMerge, lazyUpdate) {',
            '''  ECharts.prototype.setOption = function (option, notMerge, lazyUpdate) {
    // Nexum Air: shared presentation before ECharts consumes the original data.
    if (typeof window !== 'undefined' && window.NexumCharts) {
      option = window.NexumCharts.echartsOptions(option, this);
    }''')

# Modern frappe-ui uses native menu items rather than anchors. Remove the
# duplicate at its source, retaining a branded launcher when ERPNext is absent.
replace('apps/crm/frontend/src/components/UserDropdown.vue',
        'transform: (data) => [deskApp(), ...crmSiblingApps(data)],',
        "transform: (data) => [...(data.some(app => app.name === 'erpnext') ? [] : [deskApp()]), ...crmSiblingApps(data)],")
replace('apps/crm/frontend/src/components/UserDropdown.vue',
        "logo: '/assets/frappe/images/framework.png',\n    title: __('Desk'),",
        "logo: '/assets/my_branding/images/icons/erpnext_app.svg',\n    title: __('Nexum Air'),")
replace('apps/helpdesk/desk/src/composables/useApps.ts',
        'const apps = [deskApp];',
        'const apps: App[] = data.some(app => app.name === "erpnext") ? [] : [deskApp];')
replace('apps/helpdesk/desk/src/composables/useApps.ts',
        'logo: "/assets/helpdesk/desk/desk.png",\n  title: "Desk",\n  route: "/desk/helpdesk",',
        'logo: "/assets/my_branding/images/icons/erpnext_app.svg",\n  title: "Nexum Air",\n  route: "/desk",')

# Insights v3 now uses the same accessible native submenu as Drive/CRM.
path = 'apps/insights/frontend/src2/components/UserDropdown.vue'
replace(path, 'const userDropdownOptions = ref([', '''const launcherApp = {name: 'erpnext', title: 'Nexum Air', route: '/desk', logo: '/assets/my_branding/images/icons/erpnext_app.svg'}
const appMenuItem = (app: any) => ({
	label: app.title,
	icon: h('img', {src: app.logo, class: 'h-5 w-5 rounded'}),
	onClick: () => window.location.assign(app.route),
})
const userDropdownOptions = ref<any[]>([
	{label: __('Apps'), icon: 'grid', submenu: [appMenuItem(launcherApp)]},
	{label: __('Appearance'), icon: h(ToggleRight), submenu: ['Light', 'Dark', 'Automatic'].map(label => ({
		label: __(label), onClick: async () => {
			await (window as any).NexumTheme?.setChoice(label.toLowerCase())
			window.location.reload()
		},
	}))},''')
replace(path, '''	if (session.user.is_admin) {
		userDropdownOptions.value.splice(userDropdownOptions.value.length - 2, 0, {
			label: __('Switch to Desk'),
			icon: h(ToggleRight),
			onClick: () => window.open('/app', '_blank'),
		})
	}''', '''	call('frappe.apps.get_apps').then((apps: any[]) => {
		const siblings = apps.filter(app => app.name !== 'insights')
		if (!siblings.some(app => app.name === 'erpnext')) siblings.unshift(launcherApp)
		userDropdownOptions.value[0].submenu = siblings.map(appMenuItem)
	}).catch(() => {}) // the launcher remains reachable if the app list is unavailable''')

# The retained v2 interface also gets an accessible top-left Apps menu.
path = root / 'apps/insights/frontend/src/components/Sidebar.vue'
content = path.read_text()
anchor = '\n\t\t\t<div class="mt-4 flex flex-col">'
assert content.count(anchor) == 1
content = content.replace(anchor, '''
			<Dropdown :options="[{label: 'Nexum Air', icon: 'grid', onClick: () => open('/desk', '_self')}]">
				<Button class="mt-3 w-full" icon-left="grid">Apps</Button>
			</Dropdown>
''' + anchor)
path.write_text(content)
replace('apps/insights/frontend/src/components/Sidebar.vue',
        "const open = (url) => window.open(url, '_blank')",
        "const open = (url, target = '_blank') => window.open(url, target)")

# Explicit panel classes are stable styling hooks, not DOM ancestry heuristics.
replace('apps/helpdesk/desk/src/components/BarChartCard.vue',
        'default: "#3BBDE5",', 'default: "#168c83",')
replace('apps/insights/frontend/src2/charts/colors.ts',
        '\treturn Object.values(COLOR_MAP)',
        '\treturn (window as any).NexumCharts?.palette() || Object.values(COLOR_MAP)')
replace('apps/insights/frontend/src/utils/colors.ts',
        'export const getColors = (num = Object.keys(COLOR_MAP).length) => {',
        '''export const getColors = (num = Object.keys(COLOR_MAP).length) => {
	const branded = (window as any).NexumCharts?.palette()
	if (branded) return Array.from({length: num}, (_, index) => branded[index % branded.length])''')
replace('apps/helpdesk/desk/src/components/ChartCardBase.vue',
        'class="flex flex-col w-full h-full rounded-md p-4"',
        'class="nx-report-panel nx-report-kpi flex flex-col w-full h-full rounded-md p-4"')
replace('apps/helpdesk/desk/src/components/ChartCardBase.vue',
        'class="text-ink-gray-5 text-base mb-2"', 'class="nx-chart-title text-ink-gray-5 text-base mb-2"')
path = root / 'apps/crm/frontend/src/components/Dashboard/DashboardItem.vue'
content = path.read_text().replace('class="h-full w-full rounded-md bg-surface-base shadow',
                                 'class="nx-report-panel h-full w-full rounded-md bg-surface-base shadow')
content = content.replace('class="flex h-full w-full rounded shadow',
                          'class="nx-report-panel nx-report-kpi flex h-full w-full rounded shadow')
path.write_text(content)
for directory in ['src/components/Charts', 'src2/charts/components']:
    replace(f'apps/insights/frontend/{directory}/BaseChart.vue',
            'class="flex h-full w-full flex-col rounded"',
            'class="nx-report-panel flex h-full w-full flex-col rounded"')
    path = root / f'apps/insights/frontend/{directory}/ChartTitle.vue'
    text = path.read_text()
    assert text.count('<div class="') == 1
    path.write_text(text.replace('<div class="', '<div class="nx-chart-title '))
print('Applied v209 source adapters: CRM, Helpdesk, Insights and their ECharts engines')

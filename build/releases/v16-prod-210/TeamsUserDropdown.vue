<template>
  <div>
    <button ref="trigger" class="flex w-[15rem] items-center rounded-md px-2 py-2 text-left"
      :class="open ? 'bg-surface-selected shadow-sm' : 'hover:bg-surface-gray-3'"
      aria-haspopup="menu" :aria-expanded="open" aria-controls="teams-user-menu"
      @click="toggle" @keydown.down.prevent="openMenu(true)" @keydown.up.prevent="openMenu(true, true)">
      <GameplanLogo class="w-8 h-8 rounded" />
      <div class="ml-2 flex flex-col">
        <div class="text-base font-medium text-ink-gray-9 leading-none">Teams</div>
        <div class="mt-1 hidden text-sm text-ink-gray-7 sm:inline leading-none">{{ user.full_name }}</div>
      </div>
      <LucideChevronDown class="ml-auto hidden h-4 w-4 sm:inline text-ink-gray-8" />
    </button>
    <Teleport to="body">
      <div v-if="open" id="teams-user-menu" ref="menu" role="menu" aria-label="Teams"
        class="nexum-teams-menu" :style="menuPosition" @keydown="menuKeys($event, false)">
        <button ref="appsTrigger" role="menuitem" aria-haspopup="menu" :aria-expanded="appsOpen"
          aria-controls="teams-apps-menu" @mouseenter="showApps()" @click="showApps(true)"
          @keydown.right.prevent.stop="showApps(true)">
          <FeatherIcon name="grid" /><span>Apps</span><FeatherIcon name="chevron-right" />
        </button>
        <button v-for="item in items" :key="item.label" role="menuitem"
          @mouseenter="appsOpen = false" @click="activate(item)">
          <FeatherIcon :name="item.icon" /><span>{{ item.label }}</span>
        </button>
      </div>
      <div v-if="open && appsOpen" id="teams-apps-menu" ref="appsMenu" role="menu" aria-label="Apps"
        class="nexum-teams-menu" :style="appsPosition" @keydown="menuKeys($event, true)">
        <a v-for="app in appList" :key="app.name" role="menuitem" :href="app.route">
          <img :src="app.logo" alt="" /><span>{{ app.title }}</span>
        </a>
      </div>
    </Teleport>
  </div>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { createResource, FeatherIcon } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { showSettingsDialog } from '@/components/Settings/SettingsDialog.vue'
import GameplanLogo from './GameplanLogo.vue'
import { getUser } from '@/data/users'
import { session } from '@/data/session'

const user = getUser()
const router = useRouter()
const open = ref(false), appsOpen = ref(false)
const trigger = ref(), menu = ref(), appsTrigger = ref(), appsMenu = ref()
const menuPosition = ref({}), appsPosition = ref({})
const launcher = { name: 'erpnext', title: 'Nexum Air', route: '/desk', logo: '/assets/my_branding/images/icons/erpnext_app.svg' }
const apps = createResource({ url: 'frappe.apps.get_apps', cache: 'nexum-teams-apps', auto: true })
const appList = computed(() => {
  const siblings = (apps.data || []).filter(app => app.name !== 'gameplan')
  return siblings.some(app => app.name === 'erpnext') ? siblings : [launcher, ...siblings]
})
const items = computed(() => [
  { icon: 'user', label: 'My Profile', action: () => router.push({ name: 'PersonProfile', params: { personId: user.user_profile } }) },
  ...(user.isNotGuest ? [{ icon: 'settings', label: 'Settings & Members', action: () => showSettingsDialog() }] : []),
  { icon: 'moon', label: 'Toggle theme', action: toggleTheme },
  ...(user.isNotGuest && window.frappecloud_host && window.site_name ? [{ icon: 'credit-card', label: 'Subscription', action: () => window.open(`${window.frappecloud_host}/dashboard/subscription/${window.site_name}`, '_blank', 'noopener') }] : []),
  { icon: 'log-out', label: 'Log out', action: () => session.logout.submit() },
])

function positionMenus() {
  if (!open.value) return
  const rect = trigger.value.getBoundingClientRect()
  const width = Math.min(240, window.innerWidth - 16)
  menuPosition.value = { width: `${width}px`, left: `${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))}px`, top: `${Math.min(rect.bottom + 4, window.innerHeight - (menu.value?.offsetHeight || 240) - 8)}px` }
  if (appsOpen.value && appsTrigger.value) {
    const anchor = appsTrigger.value.getBoundingClientRect()
    const bounds = menu.value.getBoundingClientRect()
    const left = bounds.right + width <= window.innerWidth - 8 ? bounds.right - 1 : Math.max(8, bounds.left - width + 1)
    appsPosition.value = { width: `${width}px`, left: `${left}px`, top: `${Math.max(8, Math.min(anchor.top, window.innerHeight - (appsMenu.value?.offsetHeight || 320) - 8))}px` }
  }
}
async function openMenu(focus = false, last = false) {
  open.value = true
  await nextTick(); positionMenus()
  if (focus) focusItem(menu.value, last ? -1 : 0)
}
function toggle() { open.value ? close() : openMenu() }
function close(restore = false) {
  open.value = false; appsOpen.value = false
  if (restore) trigger.value?.focus()
}
async function showApps(focus = false) {
  appsOpen.value = true
  await nextTick(); positionMenus()
  if (focus) focusItem(appsMenu.value, 0)
}
function focusItem(container, index) {
  const entries = container?.querySelectorAll('[role="menuitem"]') || []
  entries[(index + entries.length) % entries.length]?.focus()
}
function menuKeys(event, submenu) {
  const container = submenu ? appsMenu.value : menu.value
  const entries = [...container.querySelectorAll('[role="menuitem"]')]
  const index = entries.indexOf(document.activeElement)
  if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
    event.preventDefault()
    focusItem(container, event.key === 'Home' ? 0 : event.key === 'End' ? -1 : index + (event.key === 'ArrowDown' ? 1 : -1))
  } else if (event.key === 'Escape' || (submenu && event.key === 'ArrowLeft')) {
    event.preventDefault(); event.stopPropagation()
    if (submenu) { appsOpen.value = false; appsTrigger.value?.focus() } else close(true)
  } else if (event.key === 'Tab') {
    // Return to the trigger before the browser advances out of the menu.
    close(true)
  } else if (event.key === ' ' && submenu) {
    event.preventDefault(); document.activeElement.click()
  } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
    const match = entries.findIndex((entry, i) => i > index && entry.textContent.trim().toLowerCase().startsWith(event.key.toLowerCase()))
    const fallback = entries.findIndex(entry => entry.textContent.trim().toLowerCase().startsWith(event.key.toLowerCase()))
    if (match >= 0 || fallback >= 0) { event.preventDefault(); focusItem(container, match >= 0 ? match : fallback) }
  }
}
function activate(item) { close(true); item.action() }
function outside(event) {
  if (![trigger.value, menu.value, appsMenu.value].some(element => element?.contains(event.target))) close()
}
function toggleTheme() {
  const theme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'
  document.documentElement.setAttribute('data-theme', theme)
  localStorage.setItem('theme', theme)
}
onMounted(() => {
  document.addEventListener('pointerdown', outside)
  window.addEventListener('resize', positionMenus)
  window.addEventListener('scroll', positionMenus, true)
  const theme = localStorage.getItem('theme')
  if (['light', 'dark'].includes(theme)) document.documentElement.setAttribute('data-theme', theme)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', outside)
  window.removeEventListener('resize', positionMenus)
  window.removeEventListener('scroll', positionMenus, true)
})
</script>
<style>
.nexum-teams-menu { position: fixed; z-index: 100; padding: 4px; border-radius: 12px; border: 1px solid var(--outline-gray-2, #ddd); background: var(--surface-modal, #fff); color: var(--ink-gray-8, #333); box-shadow: 0 8px 24px #0002; max-height: calc(100vh - 16px); overflow-y: auto; }
.nexum-teams-menu [role="menuitem"] { display: flex; align-items: center; gap: 8px; width: 100%; padding: 8px; border-radius: 8px; text-align: left; font-size: 14px; line-height: 20px; }
.nexum-teams-menu [role="menuitem"]:hover, .nexum-teams-menu [role="menuitem"]:focus-visible { background: var(--surface-gray-3, #eee); outline: 2px solid transparent; }
.nexum-teams-menu [role="menuitem"] > svg { width: 16px; height: 16px; flex-shrink: 0; }
.nexum-teams-menu [role="menuitem"] > img { width: 24px; height: 24px; border-radius: 6px; }
.nexum-teams-menu [role="menuitem"] > span { flex: 1; }
</style>

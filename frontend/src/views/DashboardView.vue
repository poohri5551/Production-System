<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppTopbar from '../components/AppTopbar.vue'
import ProductionView from './ProductionView.vue'
import QCView from './QCView.vue'
import ProductionStartView from './ProductionStartView.vue'
import ProductionFinishView from './ProductionFinishView.vue'
import UsersView from './UsersView.vue'
import HomeDashboardView from './HomeDashboardView.vue'
import ForecastView from './ForecastView.vue'
import { canAny } from '../permissions'
import { getNotifications, markAllNotificationsRead, markNotificationRead } from '../api/client'

const props = defineProps({
  username: {
    type: String,
    required: true,
  },
  role: {
    type: String,
    default: '',
  },
  permissions: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['logout'])

const activeMenu = ref('home')
const notifications = ref([])
const notificationUnreadCount = ref(0)
const notificationUnreadByMenu = ref({})
const notificationError = ref('')
const workflowFocusTarget = ref(null)
const workflowNavigationNotice = ref('')
let notificationPollId = null

const visibleMenus = computed(() => {
  return [
    canAny(props.permissions, ['dashboard.view']) ? { key: 'home', label: 'Home', icon: 'home' } : null,
    props.role === 'PC' ? { key: 'forecast', label: 'FORECAST', icon: 'forecast' } : null,
    canAny(props.permissions, ['production.view', 'production.manage', 'setting_die.view', 'setting_die.manage'])
      ? { key: 'production', label: 'Production & Setting Die', icon: 'production' }
      : null,
    canAny(props.permissions, ['qc.view', 'qc.manage']) ? { key: 'qc', label: 'QC Inspection', icon: 'qc' } : null,
    canAny(props.permissions, ['production_start.view', 'production_start.manage']) ? { key: 'production-start', label: 'Production Start', icon: 'start' } : null,
    canAny(props.permissions, ['production_finish.view', 'production_finish.manage']) ? { key: 'production-finish', label: 'Production Finish', icon: 'finish' } : null,
    canAny(props.permissions, ['users.manage']) ? { key: 'users', label: 'User Management', icon: 'users' } : null,
  ].filter(Boolean)
})

const activeMenuMeta = computed(() => {
  return visibleMenus.value.find((menu) => menu.key === activeMenu.value) || visibleMenus.value[0] || { label: 'No Permission', icon: 'home' }
})

function selectMenu(key) {
  if (!visibleMenus.value.some((menu) => menu.key === key)) return
  activeMenu.value = key
}

function navigateWorkflow(payload) {
  if (!payload?.menu || !visibleMenus.value.some((menu) => menu.key === payload.menu)) {
    workflowNavigationNotice.value = 'Current workflow page is not available for your role. Dashboard detail remains available.'
    return
  }
  workflowNavigationNotice.value = ''
  workflowFocusTarget.value = payload
  activeMenu.value = payload.menu
}

function handleFocusResult(result) {
  if (result?.found) {
    workflowNavigationNotice.value = `Focused Lot ${result.lotNo || workflowFocusTarget.value?.lotNo || ''}.`
    workflowFocusTarget.value = null
    return
  }
  workflowNavigationNotice.value = `Lot ${result?.lotNo || workflowFocusTarget.value?.lotNo || ''} was not found on this page. Workflow may have changed; return to Dashboard or refresh this page.`
  workflowFocusTarget.value = null
}

function returnToDashboard() {
  workflowFocusTarget.value = null
  workflowNavigationNotice.value = ''
  selectMenu('home')
}

async function fetchNotifications() {
  try {
    const data = await getNotifications()
    if (!data.success) {
      notificationError.value = data.message || 'Cannot load notifications'
      return
    }
    notifications.value = data.notifications || []
    notificationUnreadCount.value = Number(data.unread_count || 0)
    notificationUnreadByMenu.value = data.unread_by_menu || {}
    notificationError.value = ''
  } catch (error) {
    notificationError.value = 'Cannot load notifications'
  }
}

async function openNotification(notification) {
  if (!notification) return
  if (!notification.is_read) {
    try {
      await markNotificationRead(notification.id)
    } catch (error) {
      notificationError.value = 'Cannot update notification'
    }
  }
  if (notification.action_menu) {
    selectMenu(notification.action_menu)
  }
  fetchNotifications()
}

async function markAllRead() {
  try {
    const data = await markAllNotificationsRead()
    if (!data.success) {
      notificationError.value = data.message || 'Cannot update notifications'
      return
    }
    fetchNotifications()
  } catch (error) {
    notificationError.value = 'Cannot update notifications'
  }
}

watch(visibleMenus, (menus) => {
  if (!menus.some((menu) => menu.key === activeMenu.value)) {
    activeMenu.value = menus[0]?.key || ''
  }
}, { immediate: true })

onMounted(() => {
  fetchNotifications()
  notificationPollId = window.setInterval(fetchNotifications, 15000)
})

onUnmounted(() => {
  if (notificationPollId) {
    window.clearInterval(notificationPollId)
  }
})
</script>

<template>
  <div class="min-h-screen lg:grid lg:grid-cols-[280px_1fr]">
    <AppSidebar
      :menus="visibleMenus"
      :active-key="activeMenu"
      :username="username"
      :role="role"
      :menu-badges="notificationUnreadByMenu"
      @select="selectMenu"
      @logout="emit('logout')"
    />

    <main class="px-4 py-5 sm:px-6 lg:px-8">
      <AppTopbar
        :title="activeMenuMeta.label"
        :icon="activeMenuMeta.icon"
        :username="username"
        :role="role"
        :notifications="notifications"
        :notification-unread-count="notificationUnreadCount"
        :notification-error="notificationError"
        @open-notification="openNotification"
        @mark-all-notifications-read="markAllRead"
      />

      <div v-if="workflowNavigationNotice" class="mt-6 flex flex-col gap-3 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800 sm:flex-row sm:items-center sm:justify-between">
        <span>{{ workflowNavigationNotice }}</span>
        <span class="flex gap-3"><button type="button" class="font-semibold underline underline-offset-2" @click="returnToDashboard">Dashboard</button><button type="button" aria-label="Dismiss navigation notice" @click="workflowNavigationNotice = ''">Dismiss</button></span>
      </div>

      <ProductionView v-if="activeMenu === 'production'" class="mt-6" :permissions="permissions" :role="role" :focus-target="workflowFocusTarget" @focus-result="handleFocusResult" />
      <ForecastView v-else-if="activeMenu === 'forecast'" class="mt-6" />
      <QCView v-else-if="activeMenu === 'qc'" class="mt-6" :permissions="permissions" :focus-target="workflowFocusTarget" @focus-result="handleFocusResult" />
      <ProductionStartView v-else-if="activeMenu === 'production-start'" class="mt-6" :permissions="permissions" :focus-target="workflowFocusTarget" @focus-result="handleFocusResult" />
      <ProductionFinishView v-else-if="activeMenu === 'production-finish'" class="mt-6" :permissions="permissions" :focus-target="workflowFocusTarget" @focus-result="handleFocusResult" />
      <UsersView v-else-if="activeMenu === 'users'" class="mt-6" :permissions="permissions" />
      <HomeDashboardView v-else-if="activeMenu === 'home'" class="mt-6" @navigate-workflow="navigateWorkflow" />
      <section v-else class="mt-6 shell-card p-8">
        <p class="text-sm font-medium uppercase tracking-[0.22em] text-red-600">Permission denied</p>
        <h1 class="mt-3 text-3xl font-semibold tracking-tight text-slate-950">No permission</h1>
        <p class="mt-3 max-w-2xl text-slate-500">You do not have permission to view any menu.</p>
      </section>
    </main>
  </div>
</template>

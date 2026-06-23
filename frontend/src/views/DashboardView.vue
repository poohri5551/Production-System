<script setup>
import { computed, ref, watch } from 'vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppTopbar from '../components/AppTopbar.vue'
import ProductionView from './ProductionView.vue'
import QCView from './QCView.vue'
import ProductionStartView from './ProductionStartView.vue'
import ProductionFinishView from './ProductionFinishView.vue'
import UsersView from './UsersView.vue'
import HomeDashboardView from './HomeDashboardView.vue'
import { canAny } from '../permissions'

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

const visibleMenus = computed(() => {
  return [
    canAny(props.permissions, ['dashboard.view']) ? { key: 'home', label: 'Home', icon: 'home' } : null,
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

watch(visibleMenus, (menus) => {
  if (!menus.some((menu) => menu.key === activeMenu.value)) {
    activeMenu.value = menus[0]?.key || ''
  }
}, { immediate: true })
</script>

<template>
  <div class="min-h-screen lg:grid lg:grid-cols-[280px_1fr]">
    <AppSidebar
      :menus="visibleMenus"
      :active-key="activeMenu"
      :username="username"
      :role="role"
      @select="selectMenu"
      @logout="emit('logout')"
    />

    <main class="px-4 py-5 sm:px-6 lg:px-8">
      <AppTopbar :title="activeMenuMeta.label" :icon="activeMenuMeta.icon" :username="username" :role="role" />

      <ProductionView v-if="activeMenu === 'production'" class="mt-6" :permissions="permissions" />
      <QCView v-else-if="activeMenu === 'qc'" class="mt-6" :permissions="permissions" />
      <ProductionStartView v-else-if="activeMenu === 'production-start'" class="mt-6" :permissions="permissions" />
      <ProductionFinishView v-else-if="activeMenu === 'production-finish'" class="mt-6" :permissions="permissions" />
      <UsersView v-else-if="activeMenu === 'users'" class="mt-6" :permissions="permissions" />
      <HomeDashboardView v-else-if="activeMenu === 'home'" class="mt-6" />
      <section v-else class="mt-6 shell-card p-8">
        <p class="text-sm font-medium uppercase tracking-[0.22em] text-red-600">Permission denied</p>
        <h1 class="mt-3 text-3xl font-semibold tracking-tight text-slate-950">No permission</h1>
        <p class="mt-3 max-w-2xl text-slate-500">You do not have permission to view any menu.</p>
      </section>
    </main>
  </div>
</template>

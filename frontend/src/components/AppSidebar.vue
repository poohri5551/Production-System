<script setup>
defineProps({
  menus: {
    type: Array,
    required: true,
  },
  activeKey: {
    type: String,
    required: true,
  },
  username: {
    type: String,
    required: true,
  },
  role: {
    type: String,
    default: '',
  },
  menuBadges: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['select', 'logout'])
</script>

<template>
  <aside class="border-b border-blue-100 bg-white/90 p-4 shadow-soft backdrop-blur lg:min-h-screen lg:border-b-0 lg:border-r">
    <div class="flex items-center gap-3 rounded-3xl bg-blue-600 p-4 text-white">
      <div class="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/20">
        <svg class="h-7 w-7" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M4 18V9.5L9.5 13V9.5L15 13V6h4v12H4Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
          <path d="M7 18v-3h3v3M14 18v-3h3v3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
          <path d="M16 6V4h2v2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
        </svg>
      </div>
      <div>
        <p class="text-lg font-semibold leading-none">การจัดการการผลิต</p>
        <p class="mt-1 text-xs text-blue-100">Production System Management</p>
      </div>
    </div>

    <nav class="mt-6 flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible">
      <button
        v-for="menu in menus"
        :key="menu.key"
        type="button"
        class="menu-item whitespace-nowrap lg:whitespace-normal"
        :class="{ 'menu-item-active': activeKey === menu.key }"
        @click="emit('select', menu.key)"
      >
        <span class="grid h-5 w-5 place-items-center">
          <svg v-if="menu.icon === 'home'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 11.5 12 5l8 6.5V20H5.5v-8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M9.5 20v-5h5v5" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
          </svg>
          <svg v-else-if="menu.icon === 'production'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 18V9.5L9 13V9.5L14 13V7h4v11H4Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
            <path d="M7 18v-3h3v3M14 18v-3h3v3" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
          <svg v-else-if="menu.icon === 'qc'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M8 4h8l2 3v13H6V7l2-3Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
            <path d="m9 13 2 2 4-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <svg v-else-if="menu.icon === 'start'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="2" />
            <path d="M10 8.5 16 12l-6 3.5v-7Z" fill="currentColor" />
          </svg>
          <svg v-else-if="menu.icon === 'finish'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M6 20V5M6 5h10l-1.5 4L16 13H6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <svg v-else-if="menu.icon === 'users'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM4 19a5 5 0 0 1 10 0" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            <path d="M16 11.5a2.5 2.5 0 1 0 0-5M15.5 15c2.5.3 4.5 1.8 4.5 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
          <svg v-else-if="menu.icon === 'forecast'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M5 4h14v16H5V4Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
            <path d="M8 8h8M8 12h3M8 16h3M15 12v4M13 14h4" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
        </span>
        <span class="min-w-0 flex-1 text-left">{{ menu.label }}</span>
        <span
          v-if="menuBadges[menu.key] > 0"
          class="ml-auto min-w-5 rounded-full px-1.5 py-0.5 text-center text-[10px] font-bold leading-none"
          :class="activeKey === menu.key ? 'bg-white text-blue-700' : 'bg-blue-600 text-white'"
        >
          {{ menuBadges[menu.key] > 99 ? '99+' : menuBadges[menu.key] }}
        </span>
      </button>
    </nav>

    <div class="mt-6 rounded-3xl border border-blue-100 bg-blue-50 p-4 lg:mt-auto">
      <p class="text-xs uppercase tracking-[0.18em] text-blue-500">Signed in</p>
      <p class="mt-2 font-semibold text-slate-900">{{ username }}</p>
      <p class="text-sm text-slate-500">{{ role || 'No role' }}</p>
      <button
        type="button"
        class="mt-4 w-full rounded-2xl border border-blue-200 bg-white px-4 py-2 text-sm font-semibold text-blue-700 transition hover:bg-blue-600 hover:text-white"
        @click="emit('logout')"
      >
        Logout
      </button>
    </div>
  </aside>
</template>

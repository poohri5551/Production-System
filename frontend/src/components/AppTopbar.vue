<script setup>
import NotificationBell from './NotificationBell.vue'

defineProps({
  title: {
    type: String,
    required: true,
  },
  icon: {
    type: String,
    default: '',
  },
  username: {
    type: String,
    required: true,
  },
  role: {
    type: String,
    default: '',
  },
  notifications: {
    type: Array,
    default: () => [],
  },
  notificationUnreadCount: {
    type: Number,
    default: 0,
  },
  notificationError: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['open-notification', 'mark-all-notifications-read'])
</script>

<template>
  <header class="shell-card flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
    <div>
      <p class="text-sm font-medium text-blue-600">Production System Management</p>
      <h1 class="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-tight text-slate-950">
        <span class="grid h-7 w-7 place-items-center text-blue-600">
          <svg v-if="icon === 'home'" class="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 11.5 12 5l8 6.5V20H5.5v-8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M9.5 20v-5h5v5" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
          </svg>
          <svg v-else-if="icon === 'production'" class="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 18V9.5L9 13V9.5L14 13V7h4v11H4Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
            <path d="M7 18v-3h3v3M14 18v-3h3v3" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
          <svg v-else-if="icon === 'qc'" class="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M8 4h8l2 3v13H6V7l2-3Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
            <path d="m9 13 2 2 4-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <svg v-else-if="icon === 'start'" class="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="2" />
            <path d="M10 8.5 16 12l-6 3.5v-7Z" fill="currentColor" />
          </svg>
          <svg v-else-if="icon === 'finish'" class="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M6 20V5M6 5h10l-1.5 4L16 13H6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <svg v-else-if="icon === 'users'" class="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM4 19a5 5 0 0 1 10 0" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            <path d="M16 11.5a2.5 2.5 0 1 0 0-5M15.5 15c2.5.3 4.5 1.8 4.5 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
          <svg v-else-if="icon === 'forecast'" class="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M5 4h14v16H5V4Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
            <path d="M8 8h8M8 12h3M8 16h3M15 12v4M13 14h4" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
        </span>
        <span>{{ title }}</span>
      </h1>
    </div>
    <div class="flex items-center gap-3">
      <NotificationBell
        :notifications="notifications"
        :unread-count="notificationUnreadCount"
        :error="notificationError"
        @open-notification="emit('open-notification', $event)"
        @mark-all-read="emit('mark-all-notifications-read')"
      />
      <div class="flex items-center gap-3 rounded-2xl bg-blue-50 px-4 py-3">
        <div class="flex h-10 w-10 items-center justify-center rounded-2xl bg-blue-600 font-semibold text-white">
          {{ username.slice(0, 1).toUpperCase() }}
        </div>
        <div>
          <p class="text-sm font-semibold text-slate-900">{{ username }}</p>
          <p class="text-xs text-slate-500">{{ role || 'No role' }}</p>
        </div>
      </div>
    </div>
  </header>
</template>

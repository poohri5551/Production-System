<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  notifications: {
    type: Array,
    default: () => [],
  },
  unreadCount: {
    type: Number,
    default: 0,
  },
  error: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['open-notification', 'mark-all-read'])
const isOpen = ref(false)

const badgeLabel = computed(() => (props.unreadCount > 99 ? '99+' : String(props.unreadCount)))
const hasNotifications = computed(() => props.notifications.length > 0)

function formatDate(value) {
  if (!value) return ''
  const date = new Date(String(value).replace(' GMT', ''))
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = (number) => String(number).padStart(2, '0')
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function openNotification(notification) {
  emit('open-notification', notification)
  isOpen.value = false
}
</script>

<template>
  <div class="relative">
    <button
      type="button"
      class="relative grid h-11 w-11 place-items-center rounded-2xl border border-blue-100 bg-white text-blue-700 shadow-sm transition hover:bg-blue-50"
      title="Notifications"
      @click="isOpen = !isOpen"
    >
      <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M18 9a6 6 0 1 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        <path d="M10 21h4" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
      </svg>
      <span
        v-if="unreadCount > 0"
        class="absolute -right-1 -top-1 min-w-5 rounded-full bg-red-500 px-1.5 py-0.5 text-center text-[10px] font-bold leading-none text-white"
      >
        {{ badgeLabel }}
      </span>
    </button>

    <div
      v-if="isOpen"
      class="absolute right-0 z-40 mt-3 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-2xl"
    >
      <div class="flex items-center justify-between border-b border-blue-100 px-4 py-3">
        <div>
          <p class="text-sm font-semibold text-slate-900">Notifications</p>
          <p class="text-xs text-slate-500">{{ unreadCount }} unread</p>
        </div>
        <button
          type="button"
          class="rounded-xl px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-50 disabled:cursor-not-allowed disabled:text-slate-400"
          :disabled="unreadCount === 0"
          @click="emit('mark-all-read')"
        >
          Mark all read
        </button>
      </div>

      <p v-if="error" class="border-b border-amber-100 bg-amber-50 px-4 py-3 text-xs text-amber-700">
        {{ error }}
      </p>

      <div class="max-h-96 overflow-y-auto">
        <button
          v-for="notification in notifications"
          :key="notification.id"
          type="button"
          class="block w-full border-b border-slate-100 px-4 py-3 text-left transition hover:bg-blue-50"
          :class="notification.is_read ? 'bg-white' : 'bg-blue-50/70'"
          @click="openNotification(notification)"
        >
          <div class="flex items-start gap-3">
            <span class="mt-1 h-2.5 w-2.5 rounded-full" :class="notification.is_read ? 'bg-slate-200' : 'bg-blue-600'"></span>
            <span class="min-w-0 flex-1">
              <span class="block text-sm font-semibold text-slate-900">{{ notification.title }}</span>
              <span class="mt-1 block text-xs leading-5 text-slate-600">{{ notification.message }}</span>
              <span class="mt-2 block text-[11px] text-slate-400">{{ formatDate(notification.created_at) }}</span>
            </span>
          </div>
        </button>

        <div v-if="!hasNotifications" class="px-4 py-8 text-center text-sm text-slate-500">
          No notifications
        </div>
      </div>
    </div>
  </div>
</template>

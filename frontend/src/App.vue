<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import LoginView from './views/LoginView.vue'
import DashboardView from './views/DashboardView.vue'
import { getCurrentSession, logoutSession, setAuthFailureHandler } from './api/client'

const currentUser = ref(localStorage.getItem('currentUser') || '')
const currentUserRole = ref('')
const currentPermissions = ref([])
const sessionMessage = ref('')
const hasValidatedSession = ref(!currentUser.value)
const isCheckingSession = ref(Boolean(currentUser.value))
let sessionCheckTimer = null

const isAuthenticated = computed(() => Boolean(currentUser.value) && hasValidatedSession.value)

function applySession(user, permissions = []) {
  currentUser.value = user.username || ''
  currentUserRole.value = user.role || ''
  currentPermissions.value = Array.isArray(permissions) ? permissions : []
  if (currentUser.value) {
    localStorage.setItem('currentUser', currentUser.value)
  }
}

async function handleLoginSuccess(payload) {
  applySession(
    { username: payload.username || '', role: payload.role || '' },
    payload.permissions || [],
  )
  hasValidatedSession.value = true
  sessionMessage.value = ''
  await checkSession()
}

function clearLocalAuth(message = '') {
  localStorage.removeItem('currentUser')
  currentUser.value = ''
  currentUserRole.value = ''
  currentPermissions.value = []
  hasValidatedSession.value = true
  isCheckingSession.value = false
  sessionMessage.value = message
}

async function handleLogout() {
  try {
    await logoutSession()
  } finally {
    clearLocalAuth()
  }
}

async function checkSession() {
  if (!currentUser.value) {
    hasValidatedSession.value = true
    return
  }

  isCheckingSession.value = true
  try {
    const data = await getCurrentSession()
    if (!data.success) {
      clearLocalAuth(data.message || 'Session could not be verified. Please login again.')
      return
    }

    applySession(data.user || {}, data.permissions || [])
    hasValidatedSession.value = true
  } catch (error) {
    clearLocalAuth(error.message || 'Cannot connect to backend')
  } finally {
    isCheckingSession.value = false
    hasValidatedSession.value = true
  }
}

setAuthFailureHandler((message) => {
  clearLocalAuth(message || 'Session expired or account was removed. Please login again.')
})

onMounted(() => {
  checkSession()
  sessionCheckTimer = window.setInterval(checkSession, 45000)
})

onBeforeUnmount(() => {
  if (sessionCheckTimer) {
    window.clearInterval(sessionCheckTimer)
  }
})
</script>

<template>
  <main v-if="isCheckingSession && !hasValidatedSession" class="grid min-h-screen place-items-center px-4 py-10 text-slate-500">
    Loading session...
  </main>
  <DashboardView
    v-else-if="isAuthenticated"
    :username="currentUser"
    :role="currentUserRole"
    :permissions="currentPermissions"
    @logout="handleLogout"
  />
  <LoginView v-else :session-message="sessionMessage" @login-success="handleLoginSuccess" />
</template>

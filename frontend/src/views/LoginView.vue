<script setup>
import { ref } from 'vue'
import { login } from '../api/client'

defineProps({
  sessionMessage: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['login-success'])

const username = ref('')
const password = ref('')
const errorMessage = ref('')
const isLoading = ref(false)

async function submitLogin() {
  if (isLoading.value) return

  errorMessage.value = ''
  isLoading.value = true

  try {
    const data = await login(username.value.trim(), password.value)
    if (!data.success) {
      errorMessage.value = data.message || 'Login failed'
      return
    }

    const user = data.username || username.value.trim()
    const role = data.role || ''
    localStorage.setItem('currentUser', user)
    emit('login-success', { username: user, role, permissions: data.permissions || [] })
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main class="grid min-h-screen place-items-center px-4 py-10">
    <section class="grid w-full max-w-5xl overflow-hidden rounded-[2rem] border border-blue-100 bg-white shadow-soft md:grid-cols-[1.05fr_0.95fr]">
      <div class="relative hidden bg-gradient-to-br from-blue-600 to-sky-400 p-10 text-white md:block">
        <div class="absolute inset-0 opacity-20 [background-image:radial-gradient(circle_at_20%_20%,white_0,transparent_26%),radial-gradient(circle_at_80%_10%,white_0,transparent_18%)]"></div>
        <div class="relative flex h-full flex-col justify-between">
          <div>
            <div class="mb-8 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-white/20 backdrop-blur">
              <svg class="h-7 w-7" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M4 18V9.5L9.5 13V9.5L15 13V6h4v12H4Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
                <path d="M7 18v-3h3v3M14 18v-3h3v3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                <path d="M16 6V4h2v2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
              </svg>
            </div>
            <h1 class="text-4xl font-semibold leading-tight">Production System Management</h1>
            <p class="mt-4 max-w-sm text-blue-50">
              Phase 1 Vue shell for the existing Flask + MySQL production workflow.
            </p>
          </div>
          <div class="rounded-3xl bg-white/15 p-5 backdrop-blur">
            <p class="mt-0 text-2xl font-semibold">เรื่องการขอ Username</p>
            <p class="text-sm text-blue-0">ให้ทำการติดต่อขอ User ที่ผู้ดูแลระบบ</p>
            
          </div>
        </div>
      </div>

      <div class="p-8 sm:p-10">
        <div class="mb-8">
          <p class="text-sm font-medium uppercase tracking-[0.28em] text-blue-600">Welcome</p>
          <h2 class="mt-3 text-3xl font-semibold text-slate-950">เข้าสู่ระบบ</h2>
          <p class="mt-2 text-sm text-slate-500">ใช้ username & password ที่ผู้ดูแลระบบสร้างให้</p>
        </div>

        <form class="space-y-5" @submit.prevent="submitLogin">
          <p v-if="sessionMessage" class="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            {{ sessionMessage }}
          </p>

          <label class="block">
            <span class="text-sm font-medium text-slate-700">Username</span>
            <input
              v-model="username"
              name="username"
              type="text"
              required
              autocomplete="username"
              class="mt-2 w-full rounded-2xl border border-blue-100 bg-blue-50/50 px-4 py-3 text-slate-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
              placeholder="กรอก username"
            />
          </label>

          <label class="block">
            <span class="text-sm font-medium text-slate-700">Password</span>
            <input
              v-model="password"
              name="password"
              type="password"
              required
              autocomplete="current-password"
              class="mt-2 w-full rounded-2xl border border-blue-100 bg-blue-50/50 px-4 py-3 text-slate-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
              placeholder="กรอก password"
            />
          </label>

          <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
            {{ errorMessage }}
          </p>

          <button
            type="submit"
            :disabled="isLoading"
            class="w-full rounded-2xl bg-blue-600 px-5 py-3 font-semibold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ isLoading ? 'กำลังเข้าสู่ระบบ...' : 'Login' }}
          </button>
        </form>
      </div>
    </section>
  </main>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { createUser } from '../api/client'
import { getAvailableRoles } from '../permissions'

const emit = defineEmits(['close', 'saved'])

const roles = getAvailableRoles()
const form = reactive({
  username: '',
  password: '',
  role: '',
  adminPassword: '',
})

const isSubmitting = ref(false)
const errorMessage = ref('')

const canSubmit = computed(() => {
  return Boolean(form.username.trim() && form.password && roles.includes(form.role) && form.adminPassword)
})

watch(
  () => true,
  () => {
    form.username = ''
    form.password = ''
    form.role = ''
    form.adminPassword = ''
    errorMessage.value = ''
  },
  { immediate: true },
)

async function submitForm() {
  if (isSubmitting.value) return
  if (!canSubmit.value) {
    errorMessage.value = 'Username, password, role, and admin password are required.'
    return
  }

  errorMessage.value = ''
  isSubmitting.value = true

  const formData = new FormData()
  formData.append('username', form.username.trim())
  formData.append('password', form.password)
  formData.append('role', form.role)
  formData.append('admin_password', form.adminPassword)

  try {
    const data = await createUser(formData)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot create user'
      return
    }
    emit('saved')
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
    <section class="flex max-h-[90vh] w-full max-w-xl flex-col overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-2xl">
      <div class="flex items-start justify-between gap-4 border-b border-blue-100 bg-white/95 p-6">
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">Admin only</p>
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">เพิ่มผู้ใช้งาน</h2>
          <p class="mt-1 text-sm text-slate-500">สร้างผู้ใช้งานใหม่ด้วยบทบาทที่มีอยู่</p>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500 hover:bg-slate-200" @click="emit('close')">
          Close
        </button>
      </div>

      <form class="space-y-5 overflow-y-auto p-6" @submit.prevent="submitForm">
        <label class="block">
          <span class="text-sm font-medium text-slate-700">ชื่อผู้ใช้</span>
          <input v-model="form.username" name="username" type="text" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
        </label>

        <label class="block">
          <span class="text-sm font-medium text-slate-700">รหัสผ่าน</span>
          <input v-model="form.password" name="password" type="password" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
        </label>

        <label class="block">
          <span class="text-sm font-medium text-slate-700">ตำแหน่ง</span>
          <select v-model="form.role" name="role" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100">
            <option value="">-- เลือกตำแหน่ง --</option>
            <option v-for="role in roles" :key="role" :value="role">{{ role }}</option>
          </select>
        </label>

        <label class="block">
          <span class="text-sm font-medium text-slate-700">รหัสผ่านของผู้ดูแล</span>
          <input v-model="form.adminPassword" name="admin_password" type="password" required autocomplete="current-password" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
        </label>

        <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ errorMessage }}
        </p>

        <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" class="rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="emit('close')">
            Cancel
          </button>
          <button type="submit" :disabled="isSubmitting || !canSubmit" class="rounded-2xl bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
            {{ isSubmitting ? 'Saving...' : 'Save User' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>

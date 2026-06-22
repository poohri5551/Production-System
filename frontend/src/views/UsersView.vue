<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { deleteUser, getUsers, resetUserPassword, updateUserRole } from '../api/client'
import AdminPasswordModal from '../components/AdminPasswordModal.vue'
import ResetPasswordModal from '../components/ResetPasswordModal.vue'
import UserFormModal from '../components/UserFormModal.vue'
import UsersTable from '../components/UsersTable.vue'
import { can, getAvailableRoles } from '../permissions'

const props = defineProps({
  permissions: {
    type: Array,
    default: () => [],
  },
})

const availableRoles = getAvailableRoles()
const users = ref([])
const isLoading = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')
const showUserFormModal = ref(false)

const actionState = reactive({
  isOpen: false,
  mode: 'role',
  user: null,
  isSubmitting: false,
  error: '',
})

const resetPasswordState = reactive({
  isOpen: false,
  user: null,
  isSubmitting: false,
  error: '',
})

const canManageUsers = computed(() => can(props.permissions, 'users.manage'))
const isUserActionBusy = computed(() => actionState.isSubmitting || resetPasswordState.isSubmitting)
const totalUsers = computed(() => users.value.length)
const roleCounts = computed(() => availableRoles.map((role) => ({
  role,
  count: users.value.filter((user) => user.role === role).length,
})))

onMounted(() => {
  if (canManageUsers.value) loadUsers()
})

watch(canManageUsers, (canManage) => {
  if (canManage && !users.value.length) loadUsers()
})

async function loadUsers() {
  if (!canManageUsers.value) return
  isLoading.value = true
  errorMessage.value = ''

  try {
    const data = await getUsers()
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot load users'
      users.value = []
      return
    }
    users.value = data.users || []
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isLoading.value = false
  }
}

function openUserFormModal() {
  if (!canManageUsers.value) return
  noticeMessage.value = ''
  errorMessage.value = ''
  showUserFormModal.value = true
}

function closeUserFormModal() {
  showUserFormModal.value = false
}

async function handleUserSaved() {
  showUserFormModal.value = false
  noticeMessage.value = 'User created successfully.'
  await loadUsers()
}

function openRoleModal(user) {
  if (!canManageUsers.value) return
  noticeMessage.value = ''
  actionState.mode = 'role'
  actionState.user = user
  actionState.error = ''
  actionState.isOpen = true
}

function openDeleteModal(user) {
  if (!canManageUsers.value) return
  if (user?.username === 'admin') {
    errorMessage.value = 'Cannot delete the main admin user'
    return
  }
  noticeMessage.value = ''
  actionState.mode = 'delete'
  actionState.user = user
  actionState.error = ''
  actionState.isOpen = true
}

function openResetPasswordModal(user) {
  if (!canManageUsers.value) return
  noticeMessage.value = ''
  errorMessage.value = ''
  resetPasswordState.user = user
  resetPasswordState.error = ''
  resetPasswordState.isOpen = true
}

function closeResetPasswordModal() {
  if (resetPasswordState.isSubmitting) return
  resetPasswordModalState()
}

function resetPasswordModalState() {
  resetPasswordState.isOpen = false
  resetPasswordState.user = null
  resetPasswordState.error = ''
}

function closeActionModal() {
  if (actionState.isSubmitting) return
  resetActionModal()
}

function resetActionModal() {
  actionState.isOpen = false
  actionState.user = null
  actionState.error = ''
}

async function submitAction(payload) {
  if (!canManageUsers.value || !actionState.user || actionState.isSubmitting) return
  actionState.isSubmitting = true
  actionState.error = ''

  try {
    const data = actionState.mode === 'role'
      ? await updateUserRole(actionState.user.id, payload.role, payload.adminPassword)
      : await deleteUser(actionState.user.id, payload.adminPassword)

    if (!data.success) {
      actionState.error = data.message || 'Cannot update user'
      return
    }

    noticeMessage.value = actionState.mode === 'role'
      ? `Updated role for ${actionState.user.username}.`
      : `Deleted user ${actionState.user.username}.`
    resetActionModal()
    await loadUsers()
  } catch (error) {
    actionState.error = error.message || 'Cannot connect to backend'
  } finally {
    actionState.isSubmitting = false
  }
}

async function submitResetPassword(payload) {
  if (!canManageUsers.value || !resetPasswordState.user || resetPasswordState.isSubmitting) return
  resetPasswordState.isSubmitting = true
  resetPasswordState.error = ''

  try {
    const data = await resetUserPassword(resetPasswordState.user.id, {
      new_password: payload.newPassword,
      confirm_password: payload.confirmPassword,
    })

    if (!data.success) {
      resetPasswordState.error = data.message || 'Cannot reset password'
      return
    }

    noticeMessage.value = data.message || `Reset password for ${resetPasswordState.user.username}.`
    resetPasswordModalState()
    if (data.logged_out) return
    await loadUsers()
  } catch (error) {
    resetPasswordState.error = error.message || 'Cannot connect to backend'
  } finally {
    resetPasswordState.isSubmitting = false
  }
}
</script>

<template>
  <section class="space-y-6">
    <div v-if="!canManageUsers" class="shell-card p-8">
      <p class="text-sm font-medium uppercase tracking-[0.22em] text-red-600">Permission denied</p>
      <h1 class="mt-3 text-3xl font-semibold tracking-tight text-slate-950">การจัดการผู้ใช้ (User Management)</h1>
      <p class="mt-3 max-w-2xl text-slate-500">
        หน้านี้สำหรับผู้ดูแลระบบเท่านั้น หากคุณต้องการเข้าถึงข้อมูลนี้ กรุณาติดต่อผู้ดูแลระบบ
      </p>
    </div>

    <template v-else>
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">FOR ADMIN ONLY</p>
          <h1 class="mt-2 text-3xl font-semibold tracking-tight text-slate-950">การจัดการผู้ใช้ (User Management)</h1>
          <p class="mt-2 max-w-2xl text-slate-500">
            จัดการบัญชีผู้ใช้ตาม role ที่ระบบรองรับผ่านหน้านี้ การจัดการผู้ใช้ (User Management)
          </p>
        </div>
        <button type="button" class="grid h-11 w-11 place-items-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700" title="เพิ่มผู้ใช้งาน" aria-label="เพิ่มผู้ใช้งาน" @click="openUserFormModal">
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" />
          </svg>
        </button>
      </div>

      <div class="grid gap-4 md:grid-cols-4 xl:grid-cols-8">
        <article class="rounded-3xl border border-blue-100 bg-white p-5 shadow-sm">
          <p class="text-sm text-slate-500">Total users</p>
          <p class="mt-2 text-3xl font-semibold text-slate-950">{{ totalUsers }}</p>
        </article>
        <article v-for="item in roleCounts" :key="item.role" class="rounded-3xl border border-blue-100 bg-white p-5 shadow-sm">
          <p class="text-sm text-slate-500">{{ item.role }}</p>
          <p class="mt-2 text-3xl font-semibold text-blue-700">{{ item.count }}</p>
        </article>
      </div>

      <p v-if="noticeMessage" class="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700">
        {{ noticeMessage }}
      </p>
      <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
        {{ errorMessage }}
      </p>

      <div v-if="isLoading" class="shell-card p-10 text-center text-slate-500">
        Loading users...
      </div>
      <div v-else-if="!users.length" class="shell-card p-10 text-center">
        <div class="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-3xl bg-blue-50 text-blue-500">US</div>
        <h2 class="text-lg font-semibold text-slate-900">No users found</h2>
        <p class="mt-2 text-sm text-slate-500">Add a supported role account to get started.</p>
      </div>
      <UsersTable
        v-else
        :users="users"
        :is-action-busy="isUserActionBusy"
        :can-manage-users="canManageUsers"
        @edit-role="openRoleModal"
        @reset-password="openResetPasswordModal"
        @delete-user="openDeleteModal"
      />

      <UserFormModal v-if="showUserFormModal && canManageUsers" @close="closeUserFormModal" @saved="handleUserSaved" />
      <AdminPasswordModal
        :is-open="actionState.isOpen"
        :mode="actionState.mode"
        :user="actionState.user"
        :is-submitting="actionState.isSubmitting"
        :error-message="actionState.error"
        @close="closeActionModal"
        @submit="submitAction"
      />
      <ResetPasswordModal
        :is-open="resetPasswordState.isOpen"
        :user="resetPasswordState.user"
        :is-submitting="resetPasswordState.isSubmitting"
        :error-message="resetPasswordState.error"
        @close="closeResetPasswordModal"
        @submit="submitResetPassword"
      />
    </template>
  </section>
</template>

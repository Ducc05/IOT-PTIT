<script setup lang="ts">
import { computed, ref } from 'vue'
import { auth } from '../api/auth'
import { environment } from '../config/environment'
import { profile } from '../config/profile'
import { ApiError } from '../types/api'
import { errorMessage } from '../utils/format'
import PageHeader from '../components/common/PageHeader.vue'
import AppIcon from '../components/common/AppIcon.vue'
const avatarFailed = ref(false)
const isAccount = environment.source === 'api'
const accountName = computed(() => isAccount ? auth.session.value?.full_name || 'Chưa cập nhật họ tên' : profile.name)
const studentId = computed(() => isAccount ? auth.session.value?.student_id || 'Chưa cập nhật' : profile.studentId || 'Chưa cập nhật')
const accountEmail = computed(() => isAccount ? auth.session.value?.email || 'No email provided' : profile.email)
const editing = ref(false)
const saving = ref(false)
const editName = ref('')
const editStudentId = ref('')
const editEmail = ref('')
const editError = ref('')
const saved = ref(false)
function startEdit() {
  if (!isAccount) return
  editName.value = auth.session.value?.full_name || ''
  editStudentId.value = auth.session.value?.student_id || ''
  editEmail.value = auth.session.value?.email || ''
  editError.value = ''
  saved.value = false
  editing.value = true
}
function cancelEdit() { editing.value = false; editError.value = '' }
function formError(cause: unknown) {
  if (cause instanceof ApiError) {
    for (const value of Object.values(cause.details)) {
      if (typeof value === 'string') return value
      if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
    }
  }
  return errorMessage(cause)
}
async function saveProfile() {
  const full_name = editName.value.trim()
  if (!full_name) { editError.value = 'Vui lòng nhập họ và tên.'; return }
  saving.value = true
  editError.value = ''
  try {
    await auth.updateProfile({ full_name, student_id: editStudentId.value.trim() || null, email: editEmail.value.trim() })
    editing.value = false
    saved.value = true
  } catch (cause) { editError.value = formError(cause) }
  finally { saving.value = false }
}
function validUrl(url: string) { try { return ['https:', 'http:'].includes(new URL(url).protocol) } catch { return false } }
</script>
<template>
  <div class="page profile-page" :class="{ 'profile-editing': editing }">
    <PageHeader title="Profile" subtitle=""><button v-if="isAccount" class="profile-logout" type="button" @click="auth.logout()">Logout</button></PageHeader>
    <section class="profile-summary card">
      <div class="profile-body">
        <div class="profile-avatar">
          <img v-if="!isAccount && profile.avatarUrl && !avatarFailed" :src="profile.avatarUrl" :alt="`Ảnh đại diện của ${profile.name}`" @error="avatarFailed = true" />
          <svg v-else width="120" height="120" viewBox="0 0 120 120" fill="currentColor" aria-hidden="true">
            <circle cx="60" cy="39" r="25" />
            <path d="M10 120v-10a50 50 0 0 1 100 0v10Z" />
          </svg>
        </div>
        <div class="profile-details">
          <template v-if="!editing">
            <h2><button v-if="isAccount" class="profile-name-button" type="button" @click="startEdit">{{ accountName }} <span>Sửa</span></button><template v-else>{{ accountName }}</template></h2>
            <div class="profile-metadata">
              <component :is="isAccount ? 'button' : 'span'" :type="isAccount ? 'button' : undefined" :aria-label="isAccount ? 'Chỉnh sửa mã sinh viên' : undefined" @click="startEdit">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                  <path d="M14.2799 7.28134C14.3992 7.22869 14.5005 7.14218 14.5712 7.03254C14.6418 6.9229 14.6788 6.79493 14.6774 6.6645C14.6761 6.53406 14.6365 6.40689 14.5636 6.29873C14.4907 6.19057 14.3876 6.10617 14.2672 6.056L8.5532 3.45334C8.37949 3.3741 8.19079 3.3331 7.99987 3.3331C7.80894 3.3331 7.62024 3.3741 7.44653 3.45334L1.7332 6.05334C1.61451 6.10532 1.51354 6.19076 1.44264 6.29921C1.37174 6.40767 1.33398 6.53443 1.33398 6.664C1.33398 6.79358 1.37174 6.92034 1.44264 7.02879C1.51354 7.13725 1.61451 7.22269 1.7332 7.27467L7.44653 9.88C7.62024 9.95924 7.80894 10.0002 7.99987 10.0002C8.19079 10.0002 8.37949 9.95924 8.5532 9.88L14.2799 7.28134Z" stroke="#434655" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M14.6665 6.66667V10.6667" stroke="#434655" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M4 8.33333V10.6667C4 11.1971 4.42143 11.7058 5.17157 12.0809C5.92172 12.4559 6.93913 12.6667 8 12.6667C9.06087 12.6667 10.0783 12.4559 10.8284 12.0809C11.5786 11.7058 12 11.1971 12 10.6667V8.33333" stroke="#434655" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                Mã sinh viên: {{ studentId }}
              </component>
              <component :is="isAccount ? 'button' : 'span'" :type="isAccount ? 'button' : undefined" :aria-label="isAccount ? 'Chỉnh sửa email' : undefined" @click="startEdit">
                <svg width="15" height="12" viewBox="0 0 15 12" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                  <path d="M1.5 12C1.0875 12 0.734375 11.8531 0.440625 11.5594C0.146875 11.2656 0 10.9125 0 10.5V1.5C0 1.0875 0.146875 0.734375 0.440625 0.440625C0.734375 0.146875 1.0875 0 1.5 0H13.5C13.9125 0 14.2656 0.146875 14.5594 0.440625C14.8531 0.734375 15 1.0875 15 1.5V10.5C15 10.9125 14.8531 11.2656 14.5594 11.5594C14.2656 11.8531 13.9125 12 13.5 12H1.5ZM7.5 6.75L1.5 3V10.5H13.5V3L7.5 6.75ZM7.5 5.25L13.5 1.5H1.5L7.5 5.25ZM1.5 3V1.5V3V10.5V3Z" fill="#434655"/>
                </svg>
                Email: {{ accountEmail }}
              </component>
            </div>
            <p v-if="saved" class="profile-success" role="status">Đã lưu thông tin.</p>
          </template>
          <form v-else class="profile-edit-form" @submit.prevent="saveProfile">
            <label><span>Họ và tên</span><input v-model="editName" type="text" autocomplete="name" maxlength="150" required /></label>
            <label><span>Mã sinh viên</span><input v-model="editStudentId" type="text" autocomplete="off" maxlength="32" placeholder="Chưa cập nhật" /></label>
            <label class="profile-field-full"><span>Email</span><input v-model="editEmail" type="email" autocomplete="email" maxlength="254" placeholder="Chưa cập nhật" /></label>
            <div class="profile-edit-actions"><button class="profile-save" type="submit" :disabled="saving">{{ saving ? 'Đang lưu…' : 'Lưu' }}</button><button class="profile-cancel" type="button" :disabled="saving" @click="cancelEdit">Hủy</button></div>
            <p v-if="editError" class="profile-edit-error" role="alert">{{ editError }}</p>
          </form>
        </div>
      </div>
    </section>
    <section class="profile-resources"><div class="section-heading"><h2>Project Links</h2></div>
      <div class="resource-grid"><component :is="validUrl(link.url) ? 'a' : 'div'" v-for="link in profile.links" :key="link.label" class="resource-card card" :class="{ 'resource-disabled': !validUrl(link.url) }" :href="validUrl(link.url) ? link.url : undefined" :target="validUrl(link.url) ? '_blank' : undefined" :rel="validUrl(link.url) ? 'noopener noreferrer' : undefined" :aria-disabled="!validUrl(link.url)"><span class="resource-icon"><AppIcon :name="link.icon" :size="23" /></span><div><h3>{{ link.label }}</h3><p>{{ link.description }}</p></div><AppIcon v-if="validUrl(link.url)" name="external" :size="17" /></component></div>
    </section>
  </div>
</template>

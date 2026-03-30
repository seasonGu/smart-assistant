<template>
  <div class="app-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="logo">
          <span class="logo-icon">✦</span>
          <span class="logo-text">个人智能助手</span>
        </div>
      </div>

      <nav class="sidebar-nav">
        <div class="nav-label">我的助手</div>
        <router-link
          v-for="a in assistants"
          :key="a.id"
          :to="`/chat/${a.id}`"
          class="nav-item"
          :class="{ active: $route.params.id === a.id }"
        >
          <span class="nav-icon">{{ a.icon }}</span>
          <div class="nav-info">
            <span class="nav-name">{{ a.name }}</span>
            <span class="nav-desc">{{ a.description.slice(0, 20) }}…</span>
          </div>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <!-- 已登录 -->
        <div v-if="isAdmin" class="admin-bar admin-bar--on">
          <span class="admin-dot"></span>
          <span class="admin-name">管理员</span>
          <button class="admin-logout" @click="logout">退出</button>
        </div>
        <!-- 未登录 -->
        <button v-else class="admin-login-btn" @click="showLogin = true">
          🔑 管理员登录
        </button>
      </div>
    </aside>

    <!-- Main content -->
    <main class="main-content">
      <router-view />
    </main>

    <!-- 登录弹窗 -->
    <div v-if="showLogin" class="modal-mask" @click.self="showLogin = false">
      <div class="modal">
        <div class="modal-title">管理员登录</div>
        <input
          v-model="loginForm.username"
          class="modal-input"
          placeholder="用户名"
          autocomplete="username"
        />
        <input
          v-model="loginForm.password"
          class="modal-input"
          type="password"
          placeholder="密码"
          autocomplete="current-password"
          @keydown.enter="doLogin"
        />
        <div v-if="loginError" class="modal-error">{{ loginError }}</div>
        <div class="modal-actions">
          <button class="modal-cancel" @click="showLogin = false">取消</button>
          <button class="modal-confirm" :disabled="loginLoading" @click="doLogin">
            {{ loginLoading ? '登录中…' : '登录' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, computed, ref } from 'vue'
import { useAssistantStore, useAdminStore } from './store/index.js'

const aStore = useAssistantStore()
const adminStore = useAdminStore()

const assistants = computed(() => aStore.assistants)
const isAdmin = computed(() => adminStore.isAdmin)

const showLogin = ref(false)
const loginLoading = ref(false)
const loginError = ref('')
const loginForm = ref({ username: '', password: '' })

onMounted(() => aStore.fetchAssistants())

async function doLogin() {
  loginError.value = ''
  loginLoading.value = true
  try {
    const result = await adminStore.login(loginForm.value.username, loginForm.value.password)
    if (result.success) {
      showLogin.value = false
      loginForm.value = { username: '', password: '' }
    } else {
      loginError.value = '用户名或密码错误'
    }
  } catch (e) {
    loginError.value = e.response?.data?.detail || '登录失败，请重试'
  } finally {
    loginLoading.value = false
  }
}

function logout() {
  adminStore.logout()
}
</script>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  width: 100%;
  overflow: hidden;
}

.sidebar {
  width: var(--sidebar-w);
  min-width: var(--sidebar-w);
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: 20px 16px 16px;
  border-bottom: 1px solid var(--border);
}

.logo { display: flex; align-items: center; gap: 8px; }
.logo-icon { font-size: 18px; color: var(--text); }
.logo-text { font-size: 15px; font-weight: 600; color: var(--text); letter-spacing: -0.01em; }

.sidebar-nav {
  flex: 1;
  padding: 12px 8px;
  overflow-y: auto;
}

.nav-label {
  font-size: 11px; font-weight: 500; color: var(--text3);
  text-transform: uppercase; letter-spacing: 0.06em; padding: 0 8px 8px;
}

.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 10px; border-radius: var(--radius-sm);
  text-decoration: none; color: var(--text2);
  transition: background 0.12s, color 0.12s; margin-bottom: 2px;
}
.nav-item:hover { background: var(--surface2); color: var(--text); }
.nav-item.active { background: var(--accent); color: #fff; }
.nav-item.active .nav-desc { color: rgba(255,255,255,0.6); }

.nav-icon { font-size: 18px; flex-shrink: 0; }
.nav-info { display: flex; flex-direction: column; min-width: 0; }
.nav-name { font-size: 13px; font-weight: 500; line-height: 1.3; }
.nav-desc { font-size: 11px; color: var(--text3); line-height: 1.3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border);
}

/* 管理员登录按钮 */
.admin-login-btn {
  width: 100%; padding: 7px 10px;
  font-size: 12px; color: var(--text2);
  background: none; border: 1px solid var(--border);
  border-radius: var(--radius-sm); cursor: pointer;
  transition: all 0.12s; text-align: center;
}
.admin-login-btn:hover { background: var(--surface2); color: var(--text); border-color: var(--border-md); }

/* 已登录状态 */
.admin-bar {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 8px; border-radius: var(--radius-sm);
  background: var(--surface2);
}
.admin-dot {
  width: 6px; height: 6px; border-radius: 50%; background: #4caf82; flex-shrink: 0;
}
.admin-name { font-size: 12px; color: var(--text2); flex: 1; }
.admin-logout {
  font-size: 11px; color: var(--text3); background: none; border: none;
  cursor: pointer; padding: 2px 6px; border-radius: 4px; transition: all 0.1s;
}
.admin-logout:hover { color: #e24b4a; background: #fcebeb; }

.main-content { flex: 1; overflow: hidden; display: flex; flex-direction: column; }

/* 登录弹窗 */
.modal-mask {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.35);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.modal {
  background: var(--surface); border-radius: var(--radius-lg);
  border: 1px solid var(--border); padding: 24px;
  width: 320px; display: flex; flex-direction: column; gap: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.12);
}
.modal-title { font-size: 16px; font-weight: 600; color: var(--text); }
.modal-input {
  width: 100%; padding: 9px 12px; font-size: 14px;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface2); color: var(--text); outline: none;
  transition: border-color 0.12s; font-family: inherit;
}
.modal-input:focus { border-color: var(--border-md); }
.modal-error { font-size: 12px; color: #e24b4a; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 4px; }
.modal-cancel {
  padding: 7px 16px; font-size: 13px; border: 1px solid var(--border);
  border-radius: var(--radius-sm); background: none; cursor: pointer;
  color: var(--text2); transition: all 0.12s;
}
.modal-cancel:hover { background: var(--surface2); }
.modal-confirm {
  padding: 7px 16px; font-size: 13px; border: none;
  border-radius: var(--radius-sm); background: var(--accent); color: #fff;
  cursor: pointer; transition: opacity 0.12s; font-family: inherit;
}
.modal-confirm:hover:not(:disabled) { opacity: 0.85; }
.modal-confirm:disabled { opacity: 0.4; cursor: default; }
</style>

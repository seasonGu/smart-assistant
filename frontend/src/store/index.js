import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useAssistantStore = defineStore('assistant', () => {
  const assistants = ref([])
  const loading = ref(false)

  async function fetchAssistants() {
    try {
      const res = await axios.get('/api/assistants')
      assistants.value = res.data
    } catch (e) {
      console.error('获取助手列表失败', e)
    }
  }

  return { assistants, loading, fetchAssistants }
})

export const useChatStore = defineStore('chat', () => {
  const histories = ref({})   // assistantId -> messages[]

  function getHistory(id) {
    if (!histories.value[id]) histories.value[id] = []
    return histories.value[id]
  }

  function addMessage(id, msg) {
    if (!histories.value[id]) histories.value[id] = []
    histories.value[id].push(msg)
  }

  function updateLastAssistant(id, delta) {
    const msgs = histories.value[id]
    if (!msgs || msgs.length === 0) return
    const last = msgs[msgs.length - 1]
    if (last.role === 'assistant') {
      last.content += delta
    }
  }

  function clearHistory(id) {
    histories.value[id] = []
  }

  return { histories, getHistory, addMessage, updateLastAssistant, clearHistory }
})

// ====== 管理员登录状态 ======
export const useAdminStore = defineStore('admin', () => {
  const isAdmin = ref(false)
  const token = ref('')   // "Basic xxx" 格式

  async function login(username, password) {
    const res = await axios.post('/api/admin/login', { username, password })
    if (res.data.success) {
      isAdmin.value = true
      token.value = res.data.token
      // 注入到 axios 全局 header
      axios.defaults.headers.common['Authorization'] = res.data.token
      return { success: true }
    }
    return { success: false, message: '登录失败' }
  }

  function logout() {
    isAdmin.value = false
    token.value = ''
    delete axios.defaults.headers.common['Authorization']
  }

  return { isAdmin, token, login, logout }
})

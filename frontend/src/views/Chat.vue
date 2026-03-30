<template>
  <div class="chat-root">
  <div class="chat-page" v-if="assistant">
    <!-- Header -->
    <header class="chat-header">
      <div class="header-info">
        <span class="header-icon">{{ assistant.icon }}</span>
        <div>
          <div class="header-name">{{ assistant.name }}</div>
          <div class="header-status">
            <span class="dot" :class="{ online: true }"></span>
            在线
          </div>
        </div>
      </div>
      <div class="header-actions">
        <!-- 文档助手专属：文档管理面板 -->
        <template v-if="assistant.type === 'docs'">
          <button class="action-btn" @click="showDocs = !showDocs">
            📂 文档管理 <span v-if="docFiles.length" class="badge">{{ docFiles.length }}</span>
          </button>
        </template>
        <!-- 股票助手专属：数据采集按钮（仅管理员可见） -->
        <template v-if="assistantId === 'stock' && isAdmin">
          <button class="action-btn stock-btn" :disabled="stockLoading !== ''" @click="stockFetchNames">
            {{ stockLoading === 'names' ? '获取中…' : '获取股票基本信息' }}
          </button>
          <button class="action-btn stock-btn" :disabled="stockLoading !== ''" @click="stockFetchToday">
            {{ stockLoading === 'today' ? '获取中…' : '获取当日行情' }}
          </button>
          <button class="action-btn stock-btn" :disabled="stockLoading !== ''" @click="showDatePicker = true">
            {{ stockLoading === 'date' ? '获取中…' : '获取指定日期行情' }}
          </button>
        </template>
        <button class="clear-btn" @click="clearChat">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>
          </svg>
          清空
        </button>
      </div>
    </header>

    <!-- 文档管理面板（折叠） -->
    <div v-if="assistant.type === 'docs' && showDocs" class="docs-panel">
      <div class="docs-panel-inner">
        <div v-if="isAdmin" class="docs-upload">
          <label class="upload-label">
            <input type="file" accept=".pdf,.txt,.docx,.md,.csv" multiple @change="uploadFiles" style="display:none" />
            <span>＋ 上传文档</span>
          </label>
          <span class="upload-hint">支持 PDF · TXT · Word · Markdown，可多选（最多10个）</span>
        </div>
        <div v-if="uploading" class="docs-uploading">上传中… ({{ uploadProgress }})</div>
        <div v-if="docFiles.length === 0" class="docs-empty">docs 目录暂无文档</div>
        <div v-for="f in docFiles" :key="f.name" class="doc-item">
          <span class="doc-icon">📄</span>
          <span class="doc-name">{{ f.name }}</span>
          <span class="doc-size">{{ (f.size / 1024).toFixed(0) }} KB</span>
          <button v-if="isAdmin" class="doc-del" @click="deleteFile(f.name)">✕</button>
        </div>
      </div>
    </div>

    <!-- Messages -->
    <div class="messages" ref="msgContainer">
      <!-- Welcome -->
      <div v-if="messages.length === 0" class="welcome">
        <div class="welcome-icon">{{ assistant.icon }}</div>
        <div class="welcome-title">你好，我是{{ assistant.name }}</div>
        <div class="welcome-sub">{{ assistant.description }}</div>
        <div class="suggestions">
          <button
            v-for="s in assistant.suggestions"
            :key="s"
            class="suggestion"
            @click="useSuggestion(s)"
          >{{ s }}</button>
        </div>
      </div>

      <!-- Message list -->
      <div v-for="(msg, i) in messages" :key="i" class="msg-row" :class="msg.role">
        <div v-if="msg.role === 'assistant'" class="msg-avatar">{{ assistant.icon }}</div>
        <div class="msg-bubble" :class="msg.role">
          <!-- 思考过程（可折叠） -->
          <div v-if="msg.steps && msg.steps.length" class="thinking-section">
            <button class="thinking-toggle" @click="msg._showSteps = !msg._showSteps">
              <svg class="thinking-arrow" :class="{ open: msg._showSteps }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M9 18l6-6-6-6"/></svg>
              <span class="thinking-label">思考过程</span>
              <span class="thinking-count">{{ msg.steps.length }} 步</span>
            </button>
            <div v-if="msg._showSteps" class="thinking-steps">
              <div v-for="(step, si) in msg.steps" :key="si" class="thinking-step">
                <template v-if="step.type === 'function_call'">
                  <div v-if="step.thinking" class="step-thinking">{{ step.thinking }}</div>
                  <div class="step-card call">
                    <div class="step-header">
                      <span class="step-icon">&#9881;</span>
                      <span class="step-title">调用工具：{{ step.tool }}</span>
                    </div>
                    <pre v-if="step.arguments && step.arguments.sql_input" class="step-sql">{{ step.arguments.sql_input }}</pre>
                    <pre v-else class="step-args">{{ JSON.stringify(step.arguments, null, 2) }}</pre>
                  </div>
                </template>
                <template v-if="step.type === 'function_result'">
                  <div class="step-card result">
                    <div class="step-header">
                      <span class="step-icon">&#10003;</span>
                      <span class="step-title">执行结果</span>
                    </div>
                    <div class="step-result md-body" v-html="renderMd(step.result)"></div>
                  </div>
                </template>
              </div>
            </div>
          </div>
          <!-- 最终答案 -->
          <div v-if="msg.role === 'assistant'" class="md-body" v-html="renderMd(msg.content)"></div>
          <div v-else>{{ msg.content }}</div>
          <div v-if="msg.role === 'assistant' && msg.loading" class="typing">
            <span></span><span></span><span></span>
          </div>
          <!-- 来源文档卡片 -->
          <div v-if="msg.sources && msg.sources.length" class="sources">
            <div class="sources-label">检索来源</div>
            <div v-for="(s, si) in msg.sources" :key="si" class="source-card">
              <div class="source-file">📄 {{ s.file }}</div>
              <div class="source-preview">{{ s.text.slice(0, 120) }}…</div>
              <span v-if="s.score" class="source-score">相似度 {{ s.score }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Input area -->
    <div class="input-area">
      <div class="input-box">
        <textarea
          ref="inputRef"
          v-model="inputText"
          placeholder="输入你的问题…"
          rows="1"
          @keydown.enter.exact.prevent="sendMessage"
          @input="autoResize"
        ></textarea>
        <button v-if="!sending" class="send-btn" :disabled="!inputText.trim() || sending" @click="sendMessage">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z"/>
          </svg>
        </button>
        <button v-else class="stop-btn" @click="stopGeneration" title="停止生成">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <rect x="4" y="4" width="16" height="16" rx="2"/>
          </svg>
        </button>
      </div>
      <div class="input-hint">
        <span v-if="isLimited">
          <span v-if="charCount > 0" :class="{ 'over-limit': charCount > 200 }">{{ charCount }}/200 字</span>
          <span v-if="quota >= 0" class="quota-info">· 剩余 {{ quota }}/{{ quotaTotal }} 次</span>
        </span>
        <span v-else></span>
        <span>Enter 发送 · Shift+Enter 换行</span>
      </div>
    </div>

    <!-- 股票：指定日期弹窗 -->
    <div v-if="showDatePicker" class="modal-mask" @click.self="showDatePicker = false">
      <div class="modal-sm">
        <div class="modal-title">获取指定日期行情</div>
        <input
          v-model="stockDate"
          class="modal-input"
          placeholder="输入日期，如 20260327"
          maxlength="8"
          @keydown.enter="stockFetchByDate"
        />
        <div v-if="stockMsg" class="modal-msg" :class="stockMsgType">{{ stockMsg }}</div>
        <div class="modal-actions">
          <button class="modal-cancel" @click="showDatePicker = false; stockMsg = ''">关闭</button>
          <button class="modal-confirm" :disabled="stockLoading === 'date'" @click="stockFetchByDate">
            {{ stockLoading === 'date' ? '获取中…' : '开始获取' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 操作结果 Toast -->
    <div v-if="toast" class="toast" :class="toastType">{{ toast }}</div>
  </div>

  <div v-else class="not-found">
    <p>助手不存在，<router-link to="/">返回首页</router-link></p>
  </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import axios from 'axios'
import { useAssistantStore, useChatStore, useAdminStore } from '../store/index.js'

const route = useRoute()
const aStore = useAssistantStore()
const cStore = useChatStore()
const adminStore = useAdminStore()

const assistantId = computed(() => route.params.id)
const assistant = computed(() => aStore.assistants.find(a => a.id === assistantId.value))
const messages = computed(() => cStore.getHistory(assistantId.value))
const isDocsAssistant = computed(() => assistant.value?.type === 'docs')
const isAdmin = computed(() => adminStore.isAdmin)

const inputText = ref('')
const sending = ref(false)
const msgContainer = ref(null)
const inputRef = ref(null)

// 查询限额（全局，非管理员）
const quota = ref(-1)           // -1 = 管理员不限
const quotaTotal = ref(5)
const charCount = computed(() => inputText.value.length)
const isLimited = computed(() => !isAdmin.value)  // 非管理员受限

// 停止生成
let abortController = null

// 文档面板
const showDocs = ref(false)
const docFiles = ref([])
const uploading = ref(false)
const uploadProgress = ref('')

// 股票操作
const stockLoading = ref('')        // 'names' | 'today' | 'date' | ''
const showDatePicker = ref(false)
const stockDate = ref('')
const stockMsg = ref('')
const stockMsgType = ref('ok')      // 'ok' | 'err'

// Toast 通知
const toast = ref('')
const toastType = ref('ok')

marked.setOptions({ breaks: true })

function renderMd(text) {
  if (!text) return ''
  return marked.parse(text)
}

function scrollToBottom() {
  nextTick(() => {
    if (msgContainer.value)
      msgContainer.value.scrollTop = msgContainer.value.scrollHeight
  })
}

function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 140) + 'px'
}

function useSuggestion(text) {
  inputText.value = text
  nextTick(() => inputRef.value?.focus())
}

function clearChat() {
  cStore.clearHistory(assistantId.value)
}

// ====== Toast ======
function showToast(msg, type = 'ok', duration = 3000) {
  toast.value = msg
  toastType.value = type
  setTimeout(() => { toast.value = '' }, duration)
}

// ====== 管理员请求头 ======
function authHeaders() {
  return adminStore.token ? { Authorization: adminStore.token } : {}
}

// ====== 查询限额（全局） ======
async function loadQuota() {
  try {
    const res = await axios.get('/api/quota', { headers: authHeaders() })
    quota.value = res.data.remaining
    quotaTotal.value = res.data.total
  } catch {}
}

// ====== 停止生成 ======
function stopGeneration() {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  sending.value = false

  // 结束 loading 状态
  const msgs = cStore.histories[assistantId.value]
  if (msgs?.length) {
    const last = msgs[msgs.length - 1]
    if (last.role === 'assistant') {
      last.loading = false
      if (!last.content) last.content = '（已停止生成）'
    }
  }
}

// ====== 文档管理 ======
async function loadDocFiles() {
  if (!isDocsAssistant.value) return
  try {
    const res = await axios.get('/api/docs/files')
    docFiles.value = res.data
  } catch {}
}

async function uploadFiles(e) {
  const fileList = Array.from(e.target.files || [])
  if (!fileList.length) return
  if (fileList.length > 10) {
    showToast('单次最多上传 10 个文件', 'err')
    e.target.value = ''
    return
  }

  const form = new FormData()
  fileList.forEach(f => form.append('files', f))

  uploading.value = true
  uploadProgress.value = `${fileList.length} 个文件`
  try {
    const res = await axios.post('/api/docs/upload', form, { headers: authHeaders() })
    await loadDocFiles()
    showToast(res.data.message)
  } catch (err) {
    showToast('上传失败：' + (err.response?.data?.detail || err.message), 'err')
  } finally {
    uploading.value = false
    uploadProgress.value = ''
    e.target.value = ''
  }
}

async function deleteFile(name) {
  if (!confirm(`确认删除 ${name}？`)) return
  try {
    await axios.delete(`/api/docs/files/${encodeURIComponent(name)}`, { headers: authHeaders() })
    await loadDocFiles()
    showToast(`${name} 已删除`)
  } catch (err) {
    showToast('删除失败：' + (err.response?.data?.detail || err.message), 'err')
  }
}

// ====== 股票数据采集 ======

async function stockFetchNames() {
  stockLoading.value = 'names'
  try {
    const res = await axios.post('/api/stock/fetch-names', {}, { headers: authHeaders() })
    showToast(`✓ ${res.data.message}`)
  } catch (e) {
    showToast('失败：' + (e.response?.data?.detail || e.message), 'err', 5000)
  } finally {
    stockLoading.value = ''
  }
}

async function stockFetchToday() {
  stockLoading.value = 'today'
  try {
    const res = await axios.post('/api/stock/fetch-today', {}, { headers: authHeaders() })
    showToast(`✓ ${res.data.message}`)
  } catch (e) {
    showToast('失败：' + (e.response?.data?.detail || e.message), 'err', 5000)
  } finally {
    stockLoading.value = ''
  }
}

async function stockFetchByDate() {
  if (!stockDate.value || stockDate.value.length !== 8) {
    stockMsg.value = '请输入 8 位日期，如 20260327'
    stockMsgType.value = 'err'
    return
  }
  stockLoading.value = 'date'
  stockMsg.value = ''
  try {
    const res = await axios.post('/api/stock/fetch-by-date',
      { trade_date: stockDate.value },
      { headers: authHeaders() }
    )
    stockMsg.value = res.data.message
    stockMsgType.value = 'ok'
    showToast(`✓ ${res.data.message}`)
  } catch (e) {
    stockMsg.value = e.response?.data?.detail || e.message
    stockMsgType.value = 'err'
  } finally {
    stockLoading.value = ''
  }
}

// ====== SSE 流式读取通用函数 ======
async function readSSE(url, body, last) {
  abortController = new AbortController()

  const headers = { 'Content-Type': 'application/json' }
  if (adminStore.token) headers['Authorization'] = adminStore.token

  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal: abortController.signal,
  })

  // HTTP 错误处理（429 次数超限、400 字数超限等）
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: '请求失败' }))
    last.content = `⚠️ ${err.detail}`
    last.loading = false
    if (response.status === 429) await loadQuota()
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  // 初始化 steps 数组
  if (!last.steps) last.steps = []
  if (last._showSteps === undefined) last._showSteps = false

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed || !trimmed.startsWith('data: ')) continue
      const payload = trimmed.slice(6)
      if (payload === '[DONE]') break

      try {
        const obj = JSON.parse(payload)

        // 思考步骤（function_call / function_result）
        if (obj.step) {
          last.steps.push(obj.step)
          last._showSteps = true   // 有步骤时自动展开
          last.loading = false
          scrollToBottom()
        }

        // 最终答案增量文本
        if (obj.delta) {
          last.content += obj.delta
          last.loading = false
          scrollToBottom()
        }

        // 文档来源
        if (obj.sources) {
          last.sources = obj.sources
        }

        // 剩余次数
        if (obj.remaining !== undefined && obj.remaining >= 0) {
          quota.value = obj.remaining
        }

        // 错误
        if (obj.error) {
          last.content = `⚠️ ${obj.error}`
          last.loading = false
        }
      } catch {}
    }
  }
  last.loading = false
  abortController = null
}

// ====== 发送消息 ======
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || sending.value) return

  // 非管理员：字数限制（所有助手通用）
  if (isLimited.value && text.length > 200) {
    showToast(`问题不能超过 200 字（当前 ${text.length} 字）`, 'err')
    return
  }

  // 非管理员：次数限制
  if (isLimited.value && quota.value === 0) {
    showToast('今日查询次数已用完，请登录管理员账号或明天再试', 'err')
    return
  }

  cStore.addMessage(assistantId.value, { role: 'user', content: text })
  inputText.value = ''
  nextTick(() => {
    if (inputRef.value) inputRef.value.style.height = 'auto'
  })
  scrollToBottom()

  cStore.addMessage(assistantId.value, { role: 'assistant', content: '', loading: true })
  sending.value = true
  scrollToBottom()

  try {
    const history = cStore.getHistory(assistantId.value)
      .filter(m => !m.loading)
      .map(m => ({ role: m.role, content: m.content }))

    const msgs = cStore.histories[assistantId.value]
    const last = msgs[msgs.length - 1]

    if (isDocsAssistant.value) {
      // 文档助手 → /api/docs/chat
      await readSSE('/api/docs/chat', {
        assistant_id: assistantId.value,
        messages: history,
      }, last)
    } else {
      // 股票等其他助手 → /api/chat（流式，含思考步骤）
      await readSSE('/api/chat', {
        assistant_id: assistantId.value,
        messages: history,
      }, last)
    }
  } catch (e) {
    if (e.name === 'AbortError') return

    const msgs = cStore.histories[assistantId.value]
    const last = msgs[msgs.length - 1]
    if (last?.role === 'assistant') {
      last.content = `⚠️ 请求失败：${e.message}`
      last.loading = false
    }
  } finally {
    sending.value = false
    abortController = null
    scrollToBottom()
  }
}

watch(assistantId, () => { scrollToBottom(); loadDocFiles(); loadQuota() })
onMounted(() => { scrollToBottom(); loadDocFiles(); loadQuota() })
</script>

<style scoped>
.chat-root {
  display: contents;
}
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg);
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.header-info { display: flex; align-items: center; gap: 10px; }
.header-icon { font-size: 22px; }
.header-name { font-size: 14px; font-weight: 600; }
.header-status { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text3); }
.dot { width: 6px; height: 6px; border-radius: 50%; background: #ccc; }
.dot.online { background: #4caf82; }

.header-actions { display: flex; align-items: center; gap: 8px; }

.action-btn {
  display: flex; align-items: center; gap: 5px;
  font-size: 12px; color: var(--text2); background: none; border: 1px solid var(--border);
  padding: 5px 10px; border-radius: var(--radius-sm); cursor: pointer; transition: all 0.12s;
}
.action-btn:hover { color: var(--text); border-color: var(--border-md); background: var(--surface2); }
.badge {
  background: var(--accent); color: #fff;
  font-size: 10px; border-radius: 20px; padding: 1px 6px; margin-left: 2px;
}

.clear-btn {
  display: flex; align-items: center; gap: 5px;
  font-size: 12px; color: var(--text3); background: none; border: 1px solid var(--border);
  padding: 5px 10px; border-radius: var(--radius-sm); cursor: pointer; transition: all 0.12s;
}
.clear-btn:hover { color: var(--text2); border-color: var(--border-md); background: var(--surface2); }

/* 文档管理面板 */
.docs-panel {
  border-bottom: 1px solid var(--border);
  background: var(--surface2);
  flex-shrink: 0;
}
.docs-panel-inner {
  padding: 12px 20px;
  display: flex; flex-direction: column; gap: 6px;
  max-height: 220px; overflow-y: auto;
}
.docs-upload {
  display: flex; align-items: center; gap: 10px; margin-bottom: 6px;
}
.upload-label {
  display: inline-flex; align-items: center;
  padding: 5px 12px; font-size: 12px; cursor: pointer;
  background: var(--accent); color: #fff;
  border-radius: var(--radius-sm); transition: opacity 0.12s;
}
.upload-label:hover { opacity: 0.85; }
.upload-hint { font-size: 11px; color: var(--text3); }
.docs-empty { font-size: 12px; color: var(--text3); padding: 6px 0; }
.docs-uploading { font-size: 12px; color: var(--accent); padding: 4px 0; animation: blink 1.2s infinite; }
.doc-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  font-size: 12px;
}
.doc-icon { flex-shrink: 0; }
.doc-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
.doc-size { color: var(--text3); flex-shrink: 0; }
.doc-del {
  background: none; border: none; cursor: pointer;
  color: var(--text3); font-size: 12px; padding: 2px 4px;
  border-radius: 4px; transition: all 0.1s;
}
.doc-del:hover { color: #e24b4a; background: #fcebeb; }

/* 思考过程 */
.thinking-section {
  margin-bottom: 10px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 10px;
}
.thinking-toggle {
  display: flex; align-items: center; gap: 5px;
  background: none; border: none; cursor: pointer;
  font-size: 12px; color: var(--text3); padding: 0;
  font-family: inherit; transition: color 0.12s;
}
.thinking-toggle:hover { color: var(--text2); }
.thinking-arrow {
  transition: transform 0.2s; flex-shrink: 0;
}
.thinking-arrow.open { transform: rotate(90deg); }
.thinking-label { font-weight: 500; }
.thinking-count {
  font-size: 10px; color: var(--text3);
  background: var(--surface2); border: 1px solid var(--border);
  padding: 1px 6px; border-radius: 10px;
}
.thinking-steps {
  margin-top: 8px;
  display: flex; flex-direction: column; gap: 6px;
}
.thinking-step {
  display: flex; flex-direction: column; gap: 4px;
}
.step-thinking {
  font-size: 12px; color: var(--text3); line-height: 1.5;
  padding: 0 4px;
}
.step-card {
  background: var(--surface2); border: 1px solid var(--border);
  border-radius: var(--radius-sm); padding: 8px 10px;
  font-size: 12px;
}
.step-card.call { border-left: 3px solid #6366f1; }
.step-card.result { border-left: 3px solid #4caf82; }
.step-header {
  display: flex; align-items: center; gap: 5px;
  font-weight: 500; color: var(--text2); margin-bottom: 6px;
}
.step-icon { font-size: 13px; }
.step-card.call .step-icon { color: #6366f1; }
.step-card.result .step-icon { color: #4caf82; }
.step-title { font-size: 11px; }
.step-sql, .step-args {
  background: #1e1e2e; color: #a6e3a1; border-radius: 4px;
  padding: 8px 10px; font-size: 12px; line-height: 1.5;
  overflow-x: auto; white-space: pre-wrap; word-break: break-all;
  margin: 0; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
}
.step-result {
  font-size: 12px; line-height: 1.5;
  max-height: 200px; overflow-y: auto;
}
.step-result :deep(table) {
  width: 100%; border-collapse: collapse; font-size: 11px; margin: 0;
}
.step-result :deep(th),
.step-result :deep(td) {
  border: 1px solid var(--border); padding: 3px 6px; text-align: left;
}
.step-result :deep(th) {
  background: var(--surface); font-weight: 600;
}

/* 来源卡片 */
.sources { margin-top: 10px; border-top: 1px solid var(--border); padding-top: 8px; }
.sources-label { font-size: 10px; color: var(--text3); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }
.source-card {
  background: var(--surface2); border: 1px solid var(--border);
  border-radius: var(--radius-sm); padding: 7px 10px; margin-bottom: 5px;
}
.source-file { font-size: 11px; font-weight: 500; color: var(--text2); margin-bottom: 3px; }
.source-preview { font-size: 11px; color: var(--text3); line-height: 1.5; }
.source-score {
  display: inline-block; margin-top: 4px;
  font-size: 10px; color: var(--text3);
  background: var(--surface); border: 1px solid var(--border);
  padding: 1px 6px; border-radius: 10px;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.welcome {
  display: flex; flex-direction: column; align-items: center;
  text-align: center; padding: 40px 20px; margin: auto;
}
.welcome-icon { font-size: 40px; margin-bottom: 12px; }
.welcome-title { font-size: 18px; font-weight: 600; margin-bottom: 6px; }
.welcome-sub { font-size: 13px; color: var(--text2); max-width: 360px; margin-bottom: 24px; }
.suggestions { display: flex; flex-direction: column; gap: 8px; width: 100%; max-width: 440px; }
.suggestion {
  padding: 10px 14px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-sm); font-size: 13px; color: var(--text2);
  cursor: pointer; text-align: left; transition: all 0.12s; line-height: 1.4;
}
.suggestion:hover { border-color: var(--border-md); color: var(--text); background: var(--surface); box-shadow: var(--shadow); }

.msg-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.msg-row.user { flex-direction: row-reverse; }

.msg-avatar {
  font-size: 20px;
  flex-shrink: 0;
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 50%;
}

.msg-bubble {
  max-width: 72%;
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 14px;
  line-height: 1.65;
}
.msg-bubble.user {
  background: var(--accent);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.msg-bubble.assistant {
  background: var(--surface);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
  color: var(--text);
}

.typing {
  display: flex; gap: 4px; align-items: center; margin-top: 6px;
}
.typing span {
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--text3); animation: blink 1.2s infinite;
}
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink { 0%,80%,100%{opacity:0.25} 40%{opacity:1} }

.input-area {
  padding: 14px 20px 16px;
  background: var(--surface);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.input-box {
  display: flex; align-items: flex-end; gap: 8px;
  background: var(--surface2); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 8px 8px 8px 14px;
  transition: border-color 0.12s;
}
.input-box:focus-within { border-color: var(--border-md); }

textarea {
  flex: 1; background: none; border: none; outline: none;
  font-size: 14px; color: var(--text); resize: none;
  font-family: inherit; line-height: 1.5; min-height: 22px;
}
textarea::placeholder { color: var(--text3); }

.send-btn {
  width: 32px; height: 32px; flex-shrink: 0;
  background: var(--accent); color: #fff; border: none;
  border-radius: var(--radius-sm); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: opacity 0.12s;
}
.send-btn:disabled { opacity: 0.35; cursor: default; }
.send-btn:not(:disabled):hover { opacity: 0.85; }

.stop-btn {
  width: 32px; height: 32px; flex-shrink: 0;
  background: #e24b4a; color: #fff; border: none;
  border-radius: var(--radius-sm); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: opacity 0.12s;
  animation: fadeIn 0.15s ease;
}
.stop-btn:hover { opacity: 0.85; }
@keyframes fadeIn { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }

.input-hint {
  font-size: 11px; color: var(--text3); margin-top: 6px;
  display: flex; justify-content: space-between; align-items: center;
}
.over-limit { color: #e24b4a; font-weight: 500; }
.quota-info { color: var(--text3); }

.stock-btn { font-size: 11px; padding: 5px 9px; white-space: nowrap; }
.stock-btn:disabled { opacity: 0.45; cursor: default; }

/* 日期选择弹窗 */
.modal-mask {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.35);
  display: flex; align-items: center; justify-content: center;
  z-index: 999;
}
.modal-sm {
  background: var(--surface); border-radius: var(--radius-lg);
  border: 1px solid var(--border); padding: 22px;
  width: 300px; display: flex; flex-direction: column; gap: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.12);
}
.modal-title { font-size: 14px; font-weight: 600; color: var(--text); }
.modal-input {
  width: 100%; padding: 8px 12px; font-size: 14px;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface2); color: var(--text); outline: none;
  transition: border-color 0.12s; font-family: inherit;
}
.modal-input:focus { border-color: var(--border-md); }
.modal-msg { font-size: 12px; }
.modal-msg.ok { color: #4caf82; }
.modal-msg.err { color: #e24b4a; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; }
.modal-cancel {
  padding: 6px 14px; font-size: 13px; border: 1px solid var(--border);
  border-radius: var(--radius-sm); background: none; cursor: pointer;
  color: var(--text2); transition: all 0.12s; font-family: inherit;
}
.modal-cancel:hover { background: var(--surface2); }
.modal-confirm {
  padding: 6px 14px; font-size: 13px; border: none;
  border-radius: var(--radius-sm); background: var(--accent); color: #fff;
  cursor: pointer; transition: opacity 0.12s; font-family: inherit;
}
.modal-confirm:hover:not(:disabled) { opacity: 0.85; }
.modal-confirm:disabled { opacity: 0.4; cursor: default; }

/* Toast */
.toast {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  padding: 10px 20px; border-radius: var(--radius-sm);
  font-size: 13px; z-index: 9999; pointer-events: none;
  background: #1a1a18; color: #fff;
  box-shadow: 0 4px 16px rgba(0,0,0,0.2);
  animation: fadeup 0.2s ease;
}
.toast.err { background: #a32d2d; }
@keyframes fadeup { from { opacity: 0; transform: translateX(-50%) translateY(8px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }

.not-found {
  display: flex; align-items: center; justify-content: center; height: 100%;
  font-size: 14px; color: var(--text2);
}
.not-found a { color: var(--text); }
</style>

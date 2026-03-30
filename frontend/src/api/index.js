import axios from 'axios'

export async function sendChat(assistantId, messages) {
  const res = await axios.post('/api/chat', {
    assistant_id: assistantId,
    messages,
  })
  return res.data   // { reply, steps }
}

export async function* sendChatStream(assistantId, messages) {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ assistant_id: assistantId, messages }),
  })

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop()
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim()
        if (data === '[DONE]') return
        try {
          const json = JSON.parse(data)
          if (json.delta) yield json.delta
          if (json.error) throw new Error(json.error)
        } catch {}
      }
    }
  }
}

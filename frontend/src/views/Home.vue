<template>
  <div class="home">
    <div class="hero">
      <div class="hero-icon">✦</div>
      <h1 class="hero-title">个人智能助手</h1>
      <p class="hero-sub">选择一个助手，开始对话</p>
    </div>

    <div class="cards">
      <router-link
        v-for="a in assistants"
        :key="a.id"
        :to="`/chat/${a.id}`"
        class="card"
      >
        <div class="card-icon">{{ a.icon }}</div>
        <div class="card-body">
          <div class="card-name">{{ a.name }}</div>
          <div class="card-desc">{{ a.description }}</div>
        </div>
        <div class="card-arrow">→</div>
      </router-link>

      <div class="card card-coming">
        <div class="card-icon">＋</div>
        <div class="card-body">
          <div class="card-name">更多助手</div>
          <div class="card-desc">即将上线，敬请期待</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAssistantStore } from '../store/index.js'
const store = useAssistantStore()
const assistants = computed(() => store.assistants)
</script>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 40px 24px;
  background: var(--bg);
}

.hero {
  text-align: center;
  margin-bottom: 40px;
}
.hero-icon { font-size: 36px; margin-bottom: 12px; }
.hero-title { font-size: 28px; font-weight: 600; letter-spacing: -0.02em; color: var(--text); margin-bottom: 8px; }
.hero-sub { font-size: 15px; color: var(--text2); }

.cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  max-width: 520px;
}

.card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  text-decoration: none;
  color: var(--text);
  transition: border-color 0.12s, box-shadow 0.12s;
  cursor: pointer;
}
.card:hover { border-color: var(--border-md); box-shadow: var(--shadow); }
.card-coming { opacity: 0.45; cursor: default; pointer-events: none; }

.card-icon { font-size: 26px; flex-shrink: 0; }
.card-body { flex: 1; min-width: 0; }
.card-name { font-size: 14px; font-weight: 600; margin-bottom: 2px; }
.card-desc { font-size: 12px; color: var(--text2); line-height: 1.4; }
.card-arrow { font-size: 16px; color: var(--text3); }
</style>

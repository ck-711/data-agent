<template>
  <div class="chat-app">
    <!-- ===== Header ===== -->
    <header class="chat-header">
      <div class="header-accent"></div>
      <div class="header-content">
        <div class="header-brand">
          <span class="header-icon">📊</span>
          <div class="header-text">
            <h1 class="header-title">数据查询助手</h1>
            <span class="header-subtitle">NL2SQL · 自然语言转数据查询</span>
          </div>
        </div>
        <div class="header-status">
          <span class="status-dot" :class="loading ? 'busy' : 'idle'"></span>
          <span class="status-label">{{ loading ? '查询中...' : '就绪' }}</span>
        </div>
      </div>
    </header>

    <!-- ===== Messages Area ===== -->
    <main class="chat-main" ref="messagesEl" @scroll="onScroll">
      <!-- Welcome Screen -->
      <div v-if="messages.length === 0" class="welcome-screen">
        <div class="welcome-illustration">
          <div class="illustration-icon">🔮</div>
          <div class="illustration-rings">
            <span class="ring ring-1"></span>
            <span class="ring ring-2"></span>
            <span class="ring ring-3"></span>
          </div>
        </div>
        <h2 class="welcome-title">你好，我是数据查询助手</h2>
        <p class="welcome-desc">
          用自然语言描述你的需求，我将自动生成 SQL 并返回查询结果
        </p>
        <div class="welcome-features">
          <div class="feature-item">
            <span class="feature-icon">💬</span>
            <span>自然语言提问</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">⚡</span>
            <span>智能 SQL 生成</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">📋</span>
            <span>结果表格展示</span>
          </div>
        </div>
        <div class="quick-questions-welcome">
          <p class="quick-label">💡 试试这些快捷提问：</p>
          <div class="quick-chips">
            <button
              v-for="q in quickQuestions"
              :key="q"
              class="quick-chip"
              @click="sendQuickQuestion(q)"
            >
              {{ q }}
            </button>
          </div>
        </div>
      </div>

      <!-- Chat Messages -->
      <div v-else class="messages-container">
        <div
          v-for="(msg, index) in messages"
          :key="index"
          :class="['message-row', msg.role, `msg-${msg.type}`]"
        >
          <!-- Assistant avatar -->
          <div v-if="msg.role === 'assistant'" class="avatar-wrap">
            <div class="avatar assistant-avatar">🤖</div>
          </div>

          <!-- Bubble -->
          <div class="bubble-wrap">
            <div class="bubble">
              <!-- Text -->
              <div v-if="msg.type === 'text'" class="msg-text">
                {{ msg.content }}
              </div>

              <!-- Progress Steps -->
              <div v-else-if="msg.type === 'steps'" class="msg-steps">
                <div
                  v-for="(step, sIdx) in msg.steps"
                  :key="sIdx"
                  :class="['step-item', step.status]"
                >
                  <span class="step-dot" :class="step.status">
                    <span v-if="step.status === 'success'" class="step-check">✓</span>
                    <span v-else-if="step.status === 'error'" class="step-cross">✕</span>
                  </span>
                  <span class="step-text">{{ step.text }}</span>
                </div>
              </div>

              <!-- Table -->
              <div v-else-if="msg.type === 'table'" class="msg-table">
                <div class="table-header-bar">
                  <span class="table-icon">📋</span>
                  <span class="table-label">查询结果</span>
                  <span class="table-count">{{ msg.rows.length }} 行</span>
                </div>
                <div class="table-wrap">
                  <table class="result-table">
                    <thead>
                      <tr>
                        <th v-for="col in msg.columns" :key="col">
                          {{ col }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, rIdx) in msg.rows" :key="rIdx">
                        <td v-for="col in msg.columns" :key="col">
                          {{ row[col] }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Error -->
              <div v-else-if="msg.type === 'error'" class="msg-error">
                <span class="error-icon">⚠️</span>
                <div class="error-content">
                  <span class="error-label">出错了</span>
                  <span class="error-detail">{{ msg.content }}</span>
                </div>
              </div>
            </div>
            <!-- Timestamp -->
            <span v-if="msg.ts" class="msg-time">{{ msg.ts }}</span>
          </div>

          <!-- User avatar -->
          <div v-if="msg.role === 'user'" class="avatar-wrap">
            <div class="avatar user-avatar">🧑</div>
          </div>
        </div>
        <div class="messages-bottom-spacer"></div>
      </div>
    </main>

    <!-- ===== Scroll-to-bottom button ===== -->
    <button
      v-if="showScrollBtn"
      class="scroll-btn"
      @click="scrollToBottom(true)"
      title="滚动到底部"
    >
      ↓
    </button>

    <!-- ===== Bottom Input Area ===== -->
    <div class="footer-area">
      <!-- Persistent Quick Questions -->
      <div v-if="messages.length > 0" class="quick-row">
        <div class="quick-chips quick-chips-compact">
          <button
            v-for="q in compactQuickQuestions"
            :key="q"
            class="quick-chip quick-chip-compact"
            @click="sendQuickQuestion(q)"
          >
            {{ q }}
          </button>
        </div>
      </div>

      <!-- Input Box -->
      <div class="input-wrapper">
        <div :class="['input-box', { focused: inputFocused }]">
          <span class="input-icon">💬</span>
          <input
            ref="inputEl"
            v-model="question"
            @keyup.enter="sendQuestion"
            @focus="inputFocused = true"
            @blur="inputFocused = false"
            placeholder="输入您的问题，我将为您查询数据..."
            :disabled="loading"
          />
          <span v-if="question && !loading" class="input-hint">⏎ 发送</span>
          <button
            class="send-btn"
            @click="sendQuestion"
            :disabled="loading || !question"
            :title="loading ? '查询中...' : '发送'"
          >
            <span v-if="!loading" class="send-arrow">→</span>
            <span v-else class="send-spinner"></span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref, computed } from "vue";

// ===== Constants =====
const API_URL = "/api/query";

const quickQuestions = [
  "查询最近一周的订单数据",
  "统计本月各地区的销售额",
  "查看客户消费金额排名 TOP 10",
  "分析商品分类的销售趋势",
  "统计各商品的订单量",
  "对比今年与去年的营收情况",
];

const compactQuickQuestions = [
  "最近一周订单",
  "各地区销售额",
  "客户消费 TOP 10",
  "商品销售趋势",
];

// ===== State =====
const question = ref("");
const loading = ref(false);
const messages = ref([]);
const messagesEl = ref(null);
const inputEl = ref(null);
const inputFocused = ref(false);
const showScrollBtn = ref(false);
const isNearBottom = ref(true);

// ===== Helpers =====
function timeNow() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function scrollToBottom(smooth = false) {
  const el = messagesEl.value;
  if (!el) return;
  el.scrollTo({
    top: el.scrollHeight,
    behavior: smooth ? "smooth" : "instant",
  });
}

function onScroll() {
  const el = messagesEl.value;
  if (!el) return;
  const threshold = 120;
  isNearBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
  showScrollBtn.value = !isNearBottom.value;
}

// ===== Actions =====
function sendQuickQuestion(q) {
  question.value = q;
  sendQuestion();
}

async function sendQuestion() {
  if (!question.value || loading.value) return;

  const q = question.value;
  question.value = "";
  loading.value = true;
  inputFocused.value = false;

  messages.value.push({
    role: "user",
    type: "text",
    content: q,
    ts: timeNow(),
  });

  // steps container
  const stepIndex =
    messages.value.push({
      role: "assistant",
      type: "steps",
      steps: [],
      ts: timeNow(),
    }) - 1;

  await nextTick();
  scrollToBottom();

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: q }),
    });

    if (!response.body) throw new Error("服务器未返回流");

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop();

      for (const evt of events) {
        const line = evt.trim();
        if (!line.startsWith("data:")) continue;

        let data;
        try {
          data = JSON.parse(line.replace(/^data:\s*/, ""));
        } catch {
          continue;
        }

        const steps = messages.value[stepIndex].steps;

        // progress
        if (data.type === "progress") {
          let step = steps.find((s) => s.text === data.step);
          if (!step) {
            step = { text: data.step, status: data.status };
            steps.push(step);
          } else {
            step.status = data.status;
          }
        }

        // table result
        else if (data.type === "result" && Array.isArray(data.data)) {
          messages.value.push({
            role: "assistant",
            type: "table",
            columns: Object.keys(data.data[0] || {}),
            rows: data.data,
            ts: timeNow(),
          });
        }

        // error
        else if (data.type === "error") {
          messages.value.push({
            role: "assistant",
            type: "error",
            content: data.message || "发生错误",
            ts: timeNow(),
          });
        }

        await nextTick();
        scrollToBottom();
      }
    }
  } catch (e) {
    messages.value.push({
      role: "assistant",
      type: "error",
      content: e?.message || "请求失败",
      ts: timeNow(),
    });
  } finally {
    loading.value = false;
    await nextTick();
    scrollToBottom();
  }
}
</script>

<style scoped>
/* ===== Layout ===== */
.chat-app {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: linear-gradient(180deg, #f0f4f8 0%, #f8fafc 100%);
}

/* ===== Header ===== */
.chat-header {
  position: relative;
  flex-shrink: 0;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border-light);
  z-index: 10;
}

.header-accent {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--gradient-accent);
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 var(--space-xl);
  max-width: 1200px;
  margin: 0 auto;
}

.header-brand {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.header-icon {
  font-size: 26px;
  line-height: 1;
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.header-title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--color-text);
  line-height: 1.3;
}

.header-subtitle {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-weight: 400;
}

.header-status {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-success);
  transition: background var(--transition-base);
}

.status-dot.busy {
  background: var(--color-warning);
  animation: pulse-dot 1.2s ease-in-out infinite;
}

.status-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

/* ===== Main Messages Area ===== */
.chat-main {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

/* ===== Welcome Screen ===== */
.welcome-screen {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  padding: 60px var(--space-xl) 200px;
  text-align: center;
  animation: fadeIn 0.5s ease;
}

.welcome-illustration {
  position: relative;
  width: 100px;
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--space-2xl);
}

.illustration-icon {
  font-size: 52px;
  position: relative;
  z-index: 1;
  animation: float 3s ease-in-out infinite;
}

.illustration-rings {
  position: absolute;
  inset: 0;
}

.ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid var(--color-primary-100);
  animation: pulse-dot 2.5s ease-in-out infinite;
}

.ring-2 {
  animation-delay: 0.4s;
  inset: -8px;
}

.ring-3 {
  animation-delay: 0.8s;
  inset: -16px;
}

.welcome-title {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: var(--space-sm);
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.welcome-desc {
  font-size: var(--font-size-md);
  color: var(--color-text-secondary);
  max-width: 480px;
  line-height: 1.7;
  margin-bottom: var(--space-2xl);
}

.welcome-features {
  display: flex;
  gap: var(--space-xl);
  margin-bottom: var(--space-2xl);
  flex-wrap: wrap;
  justify-content: center;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  background: var(--color-surface);
  padding: var(--space-sm) var(--space-lg);
  border-radius: var(--radius-full);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--color-border-light);
}

.feature-icon {
  font-size: 16px;
}

.quick-questions-welcome {
  max-width: 560px;
}

.quick-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin-bottom: var(--space-md);
}

.quick-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  justify-content: center;
}

.quick-chip {
  padding: 10px 18px;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  font-family: var(--font-family);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
  box-shadow: var(--shadow-sm);
}

.quick-chip:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-50);
  box-shadow: var(--shadow-glow);
  transform: translateY(-1px);
}

.quick-chip:active {
  transform: translateY(0);
}

/* ===== Messages Container ===== */
.messages-container {
  padding: var(--space-xl) 20% 200px;
}

.messages-bottom-spacer {
  height: 1px;
}

/* ===== Message Row ===== */
.message-row {
  display: flex;
  margin-bottom: var(--space-xl);
  animation: fadeInUp 0.35s ease;
  gap: var(--space-sm);
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

/* ===== Avatars ===== */
.avatar-wrap {
  flex-shrink: 0;
  padding-top: 2px;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.assistant-avatar {
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
}

.user-avatar {
  background: linear-gradient(135deg, #eef2ff, #e0e7ff);
}

/* ===== Bubble ===== */
.bubble-wrap {
  max-width: min(780px, 72%);
  display: flex;
  flex-direction: column;
}

.message-row.user .bubble-wrap {
  align-items: flex-end;
}

.message-row.assistant .bubble-wrap {
  align-items: flex-start;
}

.bubble {
  padding: 14px 18px;
  border-radius: var(--radius-lg);
  font-size: var(--font-size-base);
  line-height: 1.65;
  word-break: break-word;
}

.message-row.user .bubble {
  background: var(--gradient-primary);
  color: #fff;
  border-bottom-right-radius: var(--radius-sm);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.message-row.assistant .bubble {
  background: var(--color-surface);
  color: var(--color-text);
  border-bottom-left-radius: var(--radius-sm);
  box-shadow: var(--shadow-md);
  border: 1px solid var(--color-border-light);
}

/* Message time */
.msg-time {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: 4px;
  padding: 0 4px;
}

/* ===== Step Indicators ===== */
.msg-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: var(--font-size-sm);
}

.step-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all var(--transition-base);
  font-size: 10px;
  font-weight: 700;
  color: #fff;
}

.step-dot.running {
  background: var(--color-warning);
  animation: pulse-dot 1.2s ease-in-out infinite;
}

.step-dot.success {
  background: var(--color-success);
}

.step-dot.error {
  background: var(--color-error);
}

.step-text {
  color: var(--color-text-secondary);
}

.step-item.success .step-text {
  color: var(--color-text);
}

.step-item.error .step-text {
  color: var(--color-error);
}

/* ===== Table ===== */
.msg-table {
  max-width: 100%;
}

.table-header-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border-light);
}

.table-icon {
  font-size: 14px;
}

.table-label {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
}

.table-count {
  margin-left: auto;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  background: var(--color-bg);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.table-wrap {
  max-width: 100%;
  overflow-x: auto;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.result-table {
  width: max-content;
  min-width: 100%;
  table-layout: auto;
  border-collapse: collapse;
}

.result-table th,
.result-table td {
  padding: 10px 14px;
  white-space: nowrap;
  font-size: var(--font-size-sm);
  text-align: left;
}

.result-table thead {
  position: sticky;
  top: 0;
  z-index: 1;
}

.result-table th {
  background: linear-gradient(180deg, #f8fafc, #f1f5f9);
  font-weight: 600;
  color: var(--color-text);
  border-bottom: 2px solid var(--color-border);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.result-table td {
  border-bottom: 1px solid var(--color-border-light);
  color: var(--color-text-secondary);
}

.result-table tbody tr:last-child td {
  border-bottom: none;
}

.result-table tbody tr:nth-child(even) td {
  background: #fafbfc;
}

.result-table tbody tr:hover td {
  background: var(--color-primary-50);
}

/* ===== Error ===== */
.msg-error {
  display: flex;
  gap: var(--space-md);
  align-items: flex-start;
}

.error-icon {
  font-size: 20px;
  flex-shrink: 0;
  margin-top: 1px;
}

.error-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.error-label {
  font-weight: 600;
  color: var(--color-error);
  font-size: var(--font-size-sm);
}

.error-detail {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.5;
}

/* ===== Scroll-to-bottom ===== */
.scroll-btn {
  position: fixed;
  right: 32px;
  bottom: 140px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-lg);
  z-index: 20;
  transition: all var(--transition-fast);
  animation: fadeInUp 0.3s ease;
}

.scroll-btn:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
  box-shadow: var(--shadow-glow);
  transform: translateY(-1px);
}

/* ===== Footer Area ===== */
.footer-area {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 var(--space-lg) var(--space-xl);
  pointer-events: none;
  background: linear-gradient(0deg, rgba(248, 250, 252, 0.98) 60%, rgba(248, 250, 252, 0));
  padding-top: 40px;
}

/* ===== Persistent Quick Questions ===== */
.quick-row {
  pointer-events: auto;
  margin-bottom: var(--space-md);
  max-width: 720px;
  width: 100%;
  overflow: hidden;
}

.quick-chips-compact {
  justify-content: flex-start;
  flex-wrap: nowrap;
  overflow-x: auto;
  padding: 4px 0;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.quick-chips-compact::-webkit-scrollbar {
  display: none;
}

.quick-chip-compact {
  font-size: var(--font-size-xs);
  padding: 6px 14px;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border);
  background: rgba(255, 255, 255, 0.85);
  color: var(--color-text-secondary);
  font-family: var(--font-family);
  cursor: pointer;
  transition: all var(--transition-fast);
  backdrop-filter: blur(8px);
  flex-shrink: 0;
}

.quick-chip-compact:hover {
  border-color: var(--color-primary-light);
  color: var(--color-primary);
  background: var(--color-primary-50);
}

/* ===== Input Wrapper ===== */
.input-wrapper {
  pointer-events: auto;
  width: 100%;
  max-width: 720px;
}

.input-box {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: 6px 6px 6px 18px;
  border-radius: var(--radius-full);
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1.5px solid rgba(0, 0, 0, 0.08);
  box-shadow: var(--shadow-xl);
  transition: all var(--transition-base);
}

.input-box.focused {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-xl), var(--shadow-glow);
}

.input-box:hover {
  border-color: rgba(59, 130, 246, 0.3);
}

.input-icon {
  font-size: 18px;
  flex-shrink: 0;
  opacity: 0.6;
}

.input-box input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: var(--font-size-md);
  font-family: var(--font-family);
  color: var(--color-text);
  min-width: 0;
}

.input-box input::placeholder {
  color: var(--color-text-muted);
}

.input-box input:disabled {
  opacity: 0.6;
}

.input-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
}

.send-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background: var(--gradient-primary);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all var(--transition-fast);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
  font-size: 16px;
}

.send-btn:hover:not(:disabled) {
  background: var(--gradient-primary-hover);
  box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4);
  transform: scale(1.05);
}

.send-btn:active:not(:disabled) {
  transform: scale(0.96);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}

.send-arrow {
  font-size: 20px;
  font-weight: 600;
  line-height: 1;
}

.send-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ===== Responsive ===== */
@media (max-width: 768px) {
  .header-content {
    padding: 0 var(--space-lg);
  }

  .header-subtitle {
    display: none;
  }

  .messages-container {
    padding: var(--space-lg) var(--space-lg) 180px;
  }

  .bubble-wrap {
    max-width: 82%;
  }

  .welcome-title {
    font-size: var(--font-size-xl);
  }

  .welcome-features {
    gap: var(--space-sm);
  }

  .feature-item {
    padding: var(--space-xs) var(--space-md);
    font-size: var(--font-size-xs);
  }

  .scroll-btn {
    right: 16px;
    bottom: 130px;
  }

  .quick-row {
    padding: 0 var(--space-sm);
  }
}

@media (max-width: 480px) {
  .messages-container {
    padding: var(--space-md) var(--space-md) 170px;
  }

  .bubble-wrap {
    max-width: 88%;
  }

  .bubble {
    padding: 10px 14px;
    font-size: var(--font-size-sm);
  }

  .welcome-illustration {
    width: 80px;
    height: 80px;
  }

  .illustration-icon {
    font-size: 42px;
  }

  .input-box {
    padding: 4px 4px 4px 14px;
    gap: var(--space-sm);
  }

  .input-box input {
    font-size: var(--font-size-base);
  }

  .send-btn {
    width: 36px;
    height: 36px;
  }
}
</style>

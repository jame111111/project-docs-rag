<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, type Answer, type Citation, type Health } from "../api";
import MarkdownText from "../components/MarkdownText.vue";
defineProps<{ health?: Health }>();
const emit = defineEmits<{ open: [string, Citation?]; library: [] }>();
const question = ref("");
const submitted = ref("");
const examples = ref<string[]>([]);
const suggestions = [
  "第一次启动项目，需要先配置哪些服务？",
  "本地开发需要什么环境和依赖？",
  "部署之前有哪些必填配置？",
  "提交代码前应该运行哪些检查？",
];
const recent = ref<string[]>([]);
const answer = ref<Answer>();
const loading = ref(false);
const error = ref("");
function openRef(ref: number) {
  const citation = answer.value?.citations.find((c) => c.ref === ref);
  if (citation) emit("open", citation.doc_id, citation);
}
onMounted(async () => {
  try {
    examples.value = (await api.examples()).questions;
  } catch {
    /* 状态栏显示后端错误 */
  }
});
async function ask(value = question.value) {
  if (loading.value) return;
  question.value = value;
  if (!value.trim()) {
    error.value = "请先输入一个问题。";
    return;
  }
  if (value.trim().length > 1000) {
    error.value = "问题请控制在 1000 个字符以内。";
    return;
  }
  loading.value = true;
  error.value = "";
  answer.value = undefined;
  submitted.value = value.trim();
  recent.value = [
    submitted.value,
    ...recent.value.filter((q) => q !== submitted.value),
  ].slice(0, 5);
  try {
    answer.value = await api.ask(submitted.value);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}
</script>
<template>
  <div class="ask-layout">
    <main class="ask-main">
      <div class="intro">
        <span class="eyebrow">PROJECT DOCUMENTS · 中文问答</span>
        <h1>读懂项目，从文档开始。</h1>
        <p>
          {{
            health?.product.description ||
            "上传项目文档，查找启动、部署和贡献的步骤与依据。"
          }}
        </p>
      </div>
      <div v-if="health && health.document_count === 0" class="notice">
        资料库还是空的，先添加你想了解的项目文档。
        <button class="secondary" @click="emit('library')">
          去上传 Markdown ↗
        </button>
      </div>
      <form class="question-box" @submit.prevent="ask()">
        <label for="question">你想了解什么？</label
        ><textarea
          id="question"
          v-model="question"
          maxlength="1000"
          :placeholder="
            health?.product.question_placeholder || '请输入关于项目文档的问题'
          "
          @keydown.ctrl.enter.prevent="ask()"
        ></textarea>
        <div class="question-footer">
          <span>每次提问独立处理 · Ctrl + Enter 提交</span
          ><button class="primary" :disabled="loading" type="submit">
            {{ loading ? "正在查找与回答…" : "查找答案" }}
            <span v-if="!loading">↗</span>
          </button>
        </div>
      </form>
      <div v-if="error" class="notice error" role="alert">{{ error }}</div>
      <div v-if="loading" class="answer-panel loading" role="status">
        <span class="spinner"></span> 正在检索资料并等待模型回答…
      </div>
      <section v-else-if="answer" class="answer-panel">
        <div class="answer-heading">
          <span class="eyebrow">{{
            answer.status === "answered" ? "文档回答" : "依据不足"
          }}</span
          ><span class="muted"
            >{{ (answer.timings.total_ms / 1000).toFixed(2) }} 秒</span
          >
        </div>
        <h2>{{ submitted }}</h2>
        <MarkdownText
          :text="answer.answer"
          :citation-refs="answer.citations.map((c) => c.ref)"
          @cite="openRef"
        />
        <div v-if="answer.citations.length" class="citation-links">
          <button
            v-for="c in answer.citations"
            :key="`${c.ref}-${c.start}`"
            @click="emit('open', c.doc_id, c)"
          >
            [{{ c.ref }}] {{ c.title }}
          </button>
        </div>
        <p class="fine-print">
          引用已检查是否存在于本次资料中；答案内容仍需要结合原文核对。
        </p>
      </section>
      <section v-else-if="!loading" class="examples">
        <div class="section-label">
          <h2>{{ examples.length ? "从这些问题开始" : "可以这样提问" }}</h2>
          <span>{{
            examples.length ? "来自已导入资料" : "答案以你上传的文档为准"
          }}</span>
        </div>
        <div class="example-grid">
          <button
            v-for="(q, i) in examples.length ? examples : suggestions"
            :key="q"
            :disabled="loading"
            @click="examples.length ? ask(q) : (question = q)"
          >
            <span class="example-number">0{{ i + 1 }}</span
            ><span>{{ q }}</span
            ><span class="arrow">↗</span>
          </button>
        </div>
        <p v-if="!examples.length" class="muted">
          点击示例可填入问题。是否有答案取决于已上传资料，请先上传并重建索引。
        </p>
      </section>
      <section v-if="recent.length" class="recent">
        <h2>最近提问</h2>
        <button v-for="q in recent" :key="q" @click="ask(q)">
          {{ q }} <span>↗</span>
        </button>
        <p class="fine-print">
          仅保留本次页面内的提问记录，不用于理解后续问题。
        </p>
      </section>
    </main>
    <aside class="sources">
      <div class="section-label">
        <h2>引用来源</h2>
        <span>{{ answer?.citations.length || 0 }} 条</span>
      </div>
      <template v-if="answer?.citations.length"
        ><button
          class="source-card"
          v-for="c in answer.citations"
          :key="`${c.ref}-${c.start}`"
          @click="emit('open', c.doc_id, c)"
        >
          <span class="source-tag">[{{ c.ref }}] 原文证据</span>
          <h3>{{ c.title }}</h3>
          <p class="section-path">{{ c.section }}</p>
          <blockquote>{{ c.quote }}</blockquote>
          <span class="open-source">阅读并定位原文 ↗</span>
        </button></template
      >
      <div v-else class="empty-sources">
        <div class="book-symbol">▤</div>
        <h3>让答案有据可查</h3>
        <p>回答生成后，引用的章节与原文片段会显示在这里。</p>
      </div>
      <div class="source-note">
        <span class="dot"></span> 本地文档资料
        <p>
          问答仅检索已入库的文档；问题和检索到的片段会发送到已配置的生成服务。
        </p>
      </div>
    </aside>
  </div>
</template>

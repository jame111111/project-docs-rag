<script setup lang="ts">
import { computed, ref, watch, nextTick } from "vue";
import { api, type Citation, type DocumentBody } from "../api";
import MarkdownText from "./MarkdownText.vue";
const props = defineProps<{ docId: string; citation?: Citation }>();
const emit = defineEmits<{ close: [] }>();
const doc = ref<DocumentBody>();
const error = ref("");
const loading = ref(false);
const source = ref(!!props.citation);
const mark = ref<HTMLElement>();
const dialog = ref<HTMLElement>();
let requestId = 0;
const chars = computed(() => Array.from(doc.value?.body || ""));
const before = computed(() =>
  chars.value.slice(0, props.citation?.start || 0).join(""),
);
const match = computed(() =>
  props.citation
    ? chars.value.slice(props.citation.start, props.citation.end).join("")
    : "",
);
const after = computed(() =>
  chars.value.slice(props.citation?.end || 0).join(""),
);
watch(
  () => [props.docId, props.citation],
  async () => {
    const id = ++requestId;
    loading.value = true;
    error.value = "";
    source.value = !!props.citation;
    try {
      const result = await api.document(props.docId);
      if (id !== requestId) return;
      doc.value = result;
    } catch (e) {
      if (id === requestId) error.value = (e as Error).message;
    } finally {
      if (id === requestId) {
        loading.value = false;
        await nextTick();
        (mark.value || dialog.value)?.focus({ preventScroll: true });
        mark.value?.scrollIntoView({ block: "center" });
      }
    }
  },
  { immediate: true },
);
watch(source, async () => {
  await nextTick();
  mark.value?.scrollIntoView({ block: "center" });
});
</script>
<template>
  <div class="reader-backdrop" @click.self="emit('close')">
    <section
      class="reader"
      ref="dialog"
      tabindex="-1"
      role="dialog"
      aria-modal="true"
      aria-label="文档阅读面板"
      @keydown.esc="emit('close')"
    >
      <header class="reader-header">
        <div>
          <span class="eyebrow">资料原文</span>
          <h2>{{ doc?.title || "正在打开文档" }}</h2>
        </div>
        <button
          class="icon-button"
          aria-label="关闭文档"
          @click="emit('close')"
        >
          ×
        </button>
      </header>
      <div v-if="loading" class="loading" role="status">正在读取文档…</div>
      <div v-else-if="error" class="notice error" role="alert">{{ error }}</div>
      <template v-else-if="doc"
        ><div class="reader-meta">
          {{ doc.category }} · 采集于 {{ doc.collected_at }}
          <a
            v-if="doc.source_url"
            :href="doc.source_url"
            target="_blank"
            rel="noopener noreferrer"
            >查看来源 ↗</a
          >
        </div>
        <div v-if="citation" class="notice">
          已定位：{{ citation.section }} · 引用 [{{ citation.ref }}]
        </div>
        <div class="reader-tabs">
          <button :class="{ active: !source }" @click="source = false">
            阅读视图</button
          ><button :class="{ active: source }" @click="source = true">
            定位原文
          </button>
        </div>
        <div class="reader-content">
          <div v-if="source" class="source-text">
            <template v-if="citation"
              >{{ before }}<mark ref="mark" tabindex="0">{{ match }}</mark
              >{{ after }}</template
            ><template v-else>{{ doc.body }}</template>
          </div>
          <MarkdownText v-else :text="doc.body" />
        </div>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { api, type Health, type Citation } from "./api";
import AskPage from "./pages/AskPage.vue";
import LibraryPage from "./pages/LibraryPage.vue";
import DocumentReader from "./components/DocumentReader.vue";
const page = ref<"ask" | "library">("ask");
const health = ref<Health>();
const serviceError = ref("");
const opened = ref<{ id: string; citation?: Citation }>();
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
watch(
  () => health.value?.product.id,
  (id, previous) => {
    if (previous && id !== previous) opened.value = undefined;
  },
);
async function refresh() {
  clearTimeout(timer);
  try {
    health.value = await api.health();
    serviceError.value = "";
  } catch (e) {
    serviceError.value = (e as Error).message;
  } finally {
    if (!disposed)
      timer = setTimeout(
        refresh,
        health.value?.index.status === "building" ? 1500 : 10000,
      );
  }
}
onMounted(refresh);
onUnmounted(() => {
  disposed = true;
  clearTimeout(timer);
});
function open(id: string, citation?: Citation) {
  opened.value = { id, citation };
}
</script>
<template>
  <div class="app-shell">
    <header class="topbar">
      <a class="brand" href="#" @click.prevent="page = 'ask'"
        ><span class="brand-icon">◇</span>
        <div>
          <strong>开源项目入门助手</strong
          ><span>README · 部署文档 · 贡献指南</span>
        </div></a
      >
      <nav aria-label="主导航">
        <button :class="{ active: page === 'ask' }" @click="page = 'ask'">
          文档问答</button
        ><button
          :class="{ active: page === 'library' }"
          @click="page = 'library'"
        >
          资料库
          <span class="nav-count">{{ health?.document_count || 0 }}</span>
        </button>
      </nav>
      <span class="top-status"
        ><span
          class="dot"
          :class="{ ready: health?.index.status === 'ready' }"
        ></span
        >{{
          health?.index.status === "ready"
            ? "资料已就绪"
            : health?.index.status === "building"
              ? "索引构建中"
              : "等待建立索引"
        }}</span
      >
    </header>
    <div class="source-strip">
      {{ health?.product.name || "项目文档知识库" }} <span>·</span> 来源：{{
        health?.product.source_label || "用户上传的 Markdown 文档"
      }}
      <a
        v-if="health?.product.source_url"
        :href="health.product.source_url"
        target="_blank"
        rel="noopener noreferrer"
        >参考来源 ↗</a
      >
    </div>
    <div v-if="serviceError" class="notice error global-notice" role="alert">
      {{ serviceError }}
    </div>
    <AskPage
      v-if="page === 'ask'"
      :key="health?.product.id"
      :health="health"
      @open="open"
      @library="page = 'library'"
    /><LibraryPage
      v-else
      :key="health?.product.id"
      :health="health"
      @open="open"
      @refresh="refresh"
    />
    <footer class="app-footer">
      开源项目入门助手 <span>本地检索 · 可查看原文 · 每次提问独立处理</span>
    </footer>
    <DocumentReader
      v-if="opened"
      :doc-id="opened.id"
      :citation="opened.citation"
      @close="opened = undefined"
    />
  </div>
</template>

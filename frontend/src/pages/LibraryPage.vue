<script setup lang="ts">
import { onMounted, ref, computed, watch } from "vue";
import { api, type DocumentInfo, type Health } from "../api";
const props = defineProps<{ health?: Health }>();
const emit = defineEmits<{ open: [string]; refresh: [] }>();
const docs = ref<DocumentInfo[]>([]);
const query = ref("");
const error = ref("");
const message = ref("");
const uploading = ref(false);
const updateInput = ref<HTMLInputElement>();
const updatingDoc = ref<DocumentInfo>();
const rebuilding = ref(false);
const busy = computed(
  () => rebuilding.value || props.health?.index.status === "building",
);
const filtered = computed(() =>
  docs.value.filter((d) =>
    (d.title + d.category).toLowerCase().includes(query.value.toLowerCase()),
  ),
);
async function load() {
  try {
    docs.value = (await api.documents()).documents;
  } catch (e) {
    error.value = (e as Error).message;
  }
}
onMounted(load);
watch(
  () => props.health?.index.status,
  (status, previous) => {
    if (previous === "building" && status === "ready") {
      message.value = "索引重建完成，资料已可用于检索。";
      load();
    } else if (status === "failed") {
      message.value = "";
    }
  },
);
function chooseUpdate(doc: DocumentInfo) {
  updatingDoc.value = doc;
  updateInput.value?.click();
}
async function upload(event: Event, update = false) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  error.value = "";
  message.value = "";
  if (!file.name.toLowerCase().endsWith(".md")) {
    error.value = "只支持 .md 文件。";
    input.value = "";
    return;
  }
  if (file.size > 1048576) {
    error.value = "文件超过 1 MB 上限。";
    input.value = "";
    return;
  }
  uploading.value = true;
  try {
    if (update && updatingDoc.value) {
      await api.update(updatingDoc.value.id, file);
      message.value = "文档已更新，重建索引后即可检索新正文。";
    } else {
      await api.upload(file);
      message.value = "上传成功，重建索引后即可用于检索。";
    }
    await load();
    emit("refresh");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    uploading.value = false;
    input.value = "";
    updatingDoc.value = undefined;
  }
}
async function rebuild() {
  error.value = "";
  message.value = "";
  rebuilding.value = true;
  try {
    await api.rebuild();
    message.value = "已开始重建，请等待状态更新。";
    emit("refresh");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    rebuilding.value = false;
  }
}
</script>
<template>
  <main class="library">
    <div class="library-heading">
      <div>
        <span class="eyebrow">LOCAL KNOWLEDGE LIBRARY</span>
        <h1>资料库</h1>
        <p>添加任意项目的 README、部署文档和贡献指南，建立自己的文档知识库。</p>
      </div>
      <div class="library-actions">
        <label
          class="secondary upload-button"
          :class="{ disabled: uploading || busy }"
          >{{ uploading ? "正在上传…" : "＋ 上传 Markdown"
          }}<input
            aria-label="上传 Markdown"
            type="file"
            accept=".md,text/markdown"
            :disabled="uploading || busy"
            @change="upload" /></label
        ><button class="primary" :disabled="busy || uploading" @click="rebuild">
          {{ busy ? "正在重建…" : "重建索引" }}
        </button>
      </div>
    </div>
    <div class="notice" :class="{ error: health?.index.status === 'failed' }">
      <span
        class="dot"
        :class="{ ready: health?.index.status === 'ready' }"
      ></span
      >{{ health?.index.message || "正在读取服务状态"
      }}<span class="muted"> · {{ docs.length }} 篇文档</span>
    </div>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-if="message" class="notice success" role="status">{{ message }}</p>
    <div class="library-toolbar">
      <label for="library-search">检索资料</label
      ><input
        id="library-search"
        v-model="query"
        placeholder="按标题或分类搜索"
      /><span class="muted">{{ filtered.length }} 篇</span>
    </div>
    <div class="document-list">
      <input
        ref="updateInput"
        class="hidden-file"
        aria-label="选择更新的 Markdown"
        type="file"
        accept=".md,text/markdown"
        :disabled="busy || uploading"
        @change="upload($event, true)"
      />
      <div class="document-row list-heading">
        <span>文档 / 分类</span><span>来源</span><span>状态</span><span></span>
      </div>
      <div v-for="doc in filtered" :key="doc.id" class="document-row">
        <button
          class="document-title document-open"
          @click="emit('open', doc.id)"
        >
          <span class="document-icon">▤</span>
          <div>
            <strong>{{ doc.title }}</strong
            ><small>{{ doc.category }}</small>
          </div>
        </button>
        <span class="doc-origin"
          >{{ doc.source_label }}<small>{{ doc.collected_at }}</small></span
        ><span
          class="status-pill"
          :class="{ ready: health?.index.status === 'ready' }"
          >{{ health?.index.status === "ready" ? "已索引" : "待重建" }}</span
        ><button
          class="document-update"
          :disabled="busy || uploading"
          :aria-label="`更新 ${doc.title}`"
          @click="chooseUpdate(doc)"
        >
          更新
        </button>
      </div>
      <div v-if="!filtered.length" class="empty-list">
        没有找到文档。点击“上传 Markdown”添加项目资料，上传后重建索引即可检索。
      </div>
    </div>
    <p class="fine-print">
      仅支持 UTF-8 Markdown，单个文件不超过 1
      MB。同名文件可分别上传；替换已有文档时点击该行“更新”，再重建索引。原始
      HTML 不会执行。
    </p>
  </main>
</template>

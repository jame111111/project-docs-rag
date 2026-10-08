<script setup lang="ts">
import { computed } from "vue";
import MarkdownIt from "markdown-it";
import DOMPurify from "dompurify";
const props = defineProps<{ text: string; citationRefs?: number[] }>();
const emit = defineEmits<{ cite: [number] }>();
const md = new MarkdownIt({ html: false, linkify: false, breaks: true });
// 图片不联网加载；正文中的 HTML 仅显示为文本，链接也经净化。
md.renderer.rules.image = (tokens, index) =>
  md.utils.escapeHtml("[图片说明：" + tokens[index].content + "]");
const rendered = computed(() => {
  const text = props.citationRefs
    ? props.text.replace(/\[(\d+)\]/g, (match, ref) =>
        props.citationRefs?.includes(Number(ref))
          ? `[${ref}](#citation-${ref})`
          : match,
      )
    : props.text;
  return DOMPurify.sanitize(md.render(text));
});
function click(event: MouseEvent) {
  const link = (event.target as HTMLElement).closest("a");
  const ref = link?.getAttribute("href")?.match(/^#citation-(\d+)$/);
  if (ref) {
    event.preventDefault();
    emit("cite", Number(ref[1]));
  }
}
</script>
<template>
  <div class="markdown" @click="click" v-html="rendered"></div>
</template>

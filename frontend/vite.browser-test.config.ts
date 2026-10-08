// 只供隔离的离线浏览器流程测试；默认 vite.config.ts 仍指向真实服务。
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
export default defineConfig({
  plugins: [vue()],
  server: { port: 5174, proxy: { "/api": "http://127.0.0.1:8001" } },
});

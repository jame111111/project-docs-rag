export type IndexStatus = "missing" | "stale" | "building" | "failed" | "ready";
export interface Health {
  status: string;
  product: {
    id: string;
    name: string;
    description: string;
    source_label: string;
    source_url: string;
    question_placeholder: string;
  };
  index: {
    status: IndexStatus;
    message: string;
    parents?: number;
    children?: number;
  };
  model_configured: boolean;
  document_count: number;
}
export interface DocumentInfo {
  id: string;
  title: string;
  category: string;
  source_url: string;
  source_label: string;
  collected_at: string;
  version: string;
  index_status: "indexed" | "pending";
}
export interface DocumentBody extends DocumentInfo {
  body: string;
  offset_unit: "unicode_codepoint";
}
export interface Citation {
  ref: number;
  doc_id: string;
  title: string;
  section: string;
  quote: string;
  start: number;
  end: number;
  source_url: string;
}
export interface Answer {
  status: "answered" | "insufficient_evidence";
  answer: string;
  citations: Citation[];
  timings: { retrieval_ms: number; total_ms: number };
}
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch("/api" + url, options);
  } catch {
    throw new ApiError("network_error", "无法连接后端，请检查服务是否启动。");
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new ApiError(
      detail?.code || "request_failed",
      detail?.message ||
        (response.status === 422
          ? "输入格式无效，请检查问题或上传文件。"
          : "请求失败，请稍后重试。"),
    );
  }
  return data as T;
}
export const api = {
  health: () => request<Health>("/health"),
  examples: () => request<{ questions: string[] }>("/examples"),
  documents: (q = "") =>
    request<{ documents: DocumentInfo[] }>(
      "/documents?q=" + encodeURIComponent(q),
    ),
  document: (id: string) =>
    request<DocumentBody>("/documents/" + encodeURIComponent(id)),
  ask: (question: string) =>
    request<Answer>("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<DocumentInfo>("/documents", { method: "POST", body });
  },
  update: (id: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<DocumentInfo>("/documents/" + encodeURIComponent(id), {
      method: "PUT",
      body,
    });
  },
  rebuild: () =>
    request<{ status: string; message: string }>("/index/rebuild", {
      method: "POST",
    }),
};

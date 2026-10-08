# 20 个 GitHub README 的 600 题测试

运行日期：2026-10-07。结果来自真实 CPU BGE/Chroma/BM25 检索，不是离线假向量。

20 份独立 README、600 道中文题（480 道有依据、120 道无依据），共 3600 条三模式/双 top_k 对照。
实际索引合计 449 个父块、2045 个子块；各项目只有一份文档，未混合检索20个仓库。

**完整证据覆盖率不是回答准确率。当前没有生成模型配置，600 条默认模式生成记录全部未运行。参考答案与负例的独立人工复核尚未完成。**

正例由240个不同事实各两种措辞组成，不是480个独立事实。事实组未跨开发/最终集；开发集440题、最终集160题。快照、题集与代码哈希在首次检索前冻结，本次没有围绕最终题调参。

## 全部题的检索对照

| top_k | 模式 | 完整覆盖/480 | 覆盖率 | 平均上下文字符 | 检索中位数 ms |
|---:|---|---:|---:|---:|---:|
| 1 | 纯向量子块 | 116 | 24.17% | 248.6 | 11.94 |
| 1 | 混合检索子块 | 118 | 24.58% | 243.8 | 12.037 |
| 1 | 混合检索父块 | 204 | 42.50% | 593.9 | 11.918 |
| 5 | 纯向量子块 | 251 | 52.29% | 1211.2 | 11.245 |
| 5 | 混合检索子块 | 248 | 51.67% | 1174.5 | 11.789 |
| 5 | 混合检索父块 | 311 | 64.79% | 1618.5 | 11.776 |

字符均值和耗时包含全部题；覆盖率分母只含正例。120个无依据问题的拒答质量不能用检索命中来衡量。耗时为模型预热后单次测量，共享同题候选，不包含模型生成或源码构建，不作为生产性能承诺。

## 开发/最终集（top_k=5）

| 题集 | 正例数 | 纯向量子块 | 混合检索子块 | 混合检索父块 |
|---|---:|---:|---:|---:|
| dev | 360 | 51.94% | 52.22% | 65.83% |
| final | 120 | 53.33% | 50.00% | 61.67% |

## 两种问法（top_k=5）

| 问法 | 正例数 | 纯向量子块 | 混合检索子块 | 混合检索父块 |
|---|---:|---:|---:|---:|
| direct | 240 | 52.92% | 46.67% | 60.00% |
| colloquial | 240 | 51.67% | 56.67% | 69.58% |

这组口语改述的结果没有整体下降，但只说明这些固定问法的结果，不能外推到所有口语问题。当前使用中文向量模型检索英文原文，BM25对中文词与英文术语的映射有限，未加入翻译或问题改写。

## 逐项目（top_k=5，每项目24道正例）

| 项目及快照来源 | 纯向量子块 | 混合检索子块 | 混合检索父块 |
|---|---:|---:|---:|---:|
| [kubernetes/kubernetes](https://github.com/kubernetes/kubernetes/blob/803a939a87ba8afc927a46bca983b856b03febf0/README.md) | 14/24 (58.33%) | 13/24 (54.17%) | 13/24 (54.17%) |
| [etcd-io/etcd](https://github.com/etcd-io/etcd/blob/76d58e32b30d57a540821c9c5bbcb651fd89994c/README.md) | 12/24 (50.00%) | 11/24 (45.83%) | 14/24 (58.33%) |
| [apache/spark](https://github.com/apache/spark/blob/6d020ca9295ea5121a831e98ded48dc60061b5f5/README.md) | 14/24 (58.33%) | 15/24 (62.50%) | 19/24 (79.17%) |
| [triton-inference-server/server](https://github.com/triton-inference-server/server/blob/920fc893d21019ada670624623ffc0b7a47442bb/README.md) | 3/24 (12.50%) | 6/24 (25.00%) | 9/24 (37.50%) |
| [vllm-project/vllm](https://github.com/vllm-project/vllm/blob/7436a7f119dedd0c4d5f4d745aa6c2305ee82252/README.md) | 17/24 (70.83%) | 16/24 (66.67%) | 18/24 (75.00%) |
| [pytorch/pytorch](https://github.com/pytorch/pytorch/blob/df9918af07c403c4dfe32230637e88b5fd94ccd6/README.md) | 8/24 (33.33%) | 11/24 (45.83%) | 19/24 (79.17%) |
| [tensorflow/tensorflow](https://github.com/tensorflow/tensorflow/blob/2f3601c5c8586496018bb1a6e14b97bff728d830/README.md) | 11/24 (45.83%) | 11/24 (45.83%) | 19/24 (79.17%) |
| [ClickHouse/ClickHouse](https://github.com/ClickHouse/ClickHouse/blob/2c8a93b209e7ab712da907a194d440adfe99da54/README.md) | 17/24 (70.83%) | 13/24 (54.17%) | 15/24 (62.50%) |
| [duckdb/duckdb](https://github.com/duckdb/duckdb/blob/fa93ada028b1258926e827be7af3627979093d47/README.md) | 21/24 (87.50%) | 16/24 (66.67%) | 22/24 (91.67%) |
| [milvus-io/milvus](https://github.com/milvus-io/milvus/blob/0f34d4d512d0a08e7ad297e0d4d5396943420048/README.md) | 12/24 (50.00%) | 14/24 (58.33%) | 18/24 (75.00%) |
| [qdrant/qdrant](https://github.com/qdrant/qdrant/blob/016542aa5deb6c66380bb137badf73d54f742bde/README.md) | 11/24 (45.83%) | 11/24 (45.83%) | 14/24 (58.33%) |
| [apache/flink](https://github.com/apache/flink/blob/a47e4bf9b9ef287d5ff7f5783df993e4cef2dd1a/README.md) | 12/24 (50.00%) | 10/24 (41.67%) | 15/24 (62.50%) |
| [pingcap/tidb](https://github.com/pingcap/tidb/blob/7a3dacb52efe58d28db360ae8639d8838c376544/README.md) | 10/24 (41.67%) | 12/24 (50.00%) | 17/24 (70.83%) |
| [prometheus/prometheus](https://github.com/prometheus/prometheus/blob/97541926b9e99ce298c285e67e71ebf993e9f2ff/README.md) | 7/24 (29.17%) | 8/24 (33.33%) | 13/24 (54.17%) |
| [grafana/grafana](https://github.com/grafana/grafana/blob/8012057edda4c5f3298b774076f0665812a1e630/README.md) | 15/24 (62.50%) | 13/24 (54.17%) | 18/24 (75.00%) |
| [argoproj/argo-cd](https://github.com/argoproj/argo-cd/blob/2f3711241f94959924650c9ef554f58a7fbd4d26/README.md) | 12/24 (50.00%) | 13/24 (54.17%) | 9/24 (37.50%) |
| [opensearch-project/OpenSearch](https://github.com/opensearch-project/OpenSearch/blob/d2da1efc2b9aef893e7481921c28a2201f7cebd1/README.md) | 15/24 (62.50%) | 13/24 (54.17%) | 11/24 (45.83%) |
| [temporalio/temporal](https://github.com/temporalio/temporal/blob/e161e3bc28d4e86ce76ae5f83d12c2443e76cb8d/README.md) | 15/24 (62.50%) | 15/24 (62.50%) | 16/24 (66.67%) |
| [supabase/supabase](https://github.com/supabase/supabase/blob/808322622933f693eb292a986f6a26aba51138a9/README.md) | 17/24 (70.83%) | 17/24 (70.83%) | 19/24 (79.17%) |
| [apache/airflow](https://github.com/apache/airflow/blob/508267cda9b510013f1a8b83541472cef09ef9a1/README.md) | 8/24 (33.33%) | 10/24 (41.67%) | 13/24 (54.17%) |

## 观察到的改善与失败

- 混合检索相对纯向量：改善 29 题、退步 32 题，净少覆盖3题。当前默认RRF没有整体改善，不能写成提升。
- 父块相对混合子块：改善 85 题、退步 22 题；仍有 169 道正例未完整覆盖。增益来自补充同章节上下文，同时增加上下文字符。
- 正例中父块模式有 10 题上下文为空；超预算首块会连同后续块舍弃。长列表、HTML表格及较长不可拆单元会放大这一限制。没有在看到最终结果后改分块或预算。
- Argo CD 与 OpenSearch 等概览 README 存在父块退步；项目复杂不等于 README 内容充足。链接入口题只能回答去哪里查，不能生成链接内的配置步骤。
- 单项目索引结果不验证多个仓库混库时的跨项目误检。引用位置与父子关系已自动核对，语义正确性仍需要独立人工判断。

逐题完整候选与上下文在各项目 `retrieval.json`；代表案例见 [cases.md](cases.md)。

## 生成与工程验证

600条生成记录：`not_run / model_not_configured`；答案与引用为空，`review=unverified`。不自动给无依据问题打正确拒答分。人工表见 [answers-review.csv](answers-review.csv)，当前没有可以公布的回答准确率或拒答率。

27项离线流程测试通过，包括新增快照/600题证据完整性、事实分组隔离、可注入离线向量流程及负例不计入覆盖率。测试替身不参与本报告的真实检索数据。20个实际索引均核对父子归属、真实正文偏移和SQLite/Chroma数量。

源码与固定资料的复现命令见 [测试说明](../../github_readmes/README.md)。本报告未验证20个上游软件自身的构建和部署，也未执行其 README 命令。

证据章节名称的显示元数据已补齐。问题、参考要点、证据原文与字符区间未改动，覆盖率未重算；运行时原始题集副本在各项目 `dataset-at-run.json`，修复记录见 `metadata.json`。

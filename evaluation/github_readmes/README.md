# 20 个 GitHub 项目的 README 测试

本目录仅是测试资料。应用默认资料库、前端和检索算法不读取项目名单，也不依赖其中任意仓库。

选择复杂分布式系统、数据库、机器学习与云原生项目作为有意样本，**不是复杂度排行榜**。每项目只采集根目录 UTF-8 Markdown README，不跟随图片或链接抓取其他文档，不构建或执行上游软件。来源、完整提交号、采集日期、原始文件 SHA256 见 [sources.json](sources.json)，原始字节快照与上游许可文件在各项目目录保留。许可沿用上游，本文档和测试结果不代表上游官方结论。

每个 README 有 30 道中文题：12 个有依据事实各两种问法（24 题）与 6 道当前 README 没有足够依据的题，共 600 题、240 组不同正例事实。涉及功能、命令、前置条件、安全注意事项和资料入口；有些复杂项目的 README 只是概览，不能因此编造部署细节。负例判断仅针对已采集 README，不能推断软件缺少某项能力。

题目依据快照编写，构建脚本校验连续原文及 Unicode 字符偏移；参考答案与负例的独立人工复核仍待完成。每项目开发集22题、原最终集8题，事实组不跨两集。基线配置在首次检索前冻结。题目已在基线报告中查看，后续修改使用它们做回归，不能再称为未见过的最终验证；需要新的独立题集才能检验泛化。两种措辞共享事实，不能把600题当成600个独立事实样本。

在项目根目录运行：

```powershell
.\scripts\evaluate-github-readmes.ps1 -Phase retrieval
.\scripts\evaluate-github-readmes.ps1 -Phase answers
```

也可 `-Phase all` 一次运行两阶段。原始结果写入新的 `evaluation/results/run-github-readmes-日期-随机后缀`，不会覆盖历史结果。20个当前索引分别在 `data/runtime/github-readmes-v2/项目ID`，不混入正式资料库；原基线索引目录保留。可用 `-RuntimeRoot` 指定新的独立目录。CPU 向量模型复用，BM25 在索引时建立，问答不联网搜索。

检索阶段使用实际 BGE/Chroma/BM25，比较纯向量子块、混合检索子块、混合检索父块；两路各10候选、RRF k=60、top_k=1/5、4000字符预算。完整证据覆盖要求所有必需原文区间进入实际上下文。记录每题候选、完整上下文、字符数和检索耗时；未命中、父块预算超出及退步均保留。

生成阶段每题运行应用默认模式（混合检索父块，top_k=5），沿用真实模型接口和引用检查。没有配置模型时产生 `not_run/model_not_configured` 记录；运行错误单独保存。`answers-review.csv` 需要人工核对，未核对的准确率、误拒答、正确拒答均为未验证。检索负例会返回候选，检索覆盖率不衡量拒答质量。真实模型答案也不能仅因引用合法就判为正确。

重复本次测试不需要网络。`scripts/snapshot_github_readmes.py` 可补齐缺失快照，默认复用已有固定版本；测试新的源版本时应另存一轮快照，明确审阅并更新题目及冻结文件，不覆盖本次资料或自动沿用旧事实。

改进后的实测和固定候选预算对照见 [回归比较](../results/github-readmes-improved-2026-10-07/comparison.md)。可为自己的完整运行生成报告和比较，路径使用实际新运行目录：

```powershell
.\.venv\Scripts\python.exe scripts\report_github_readmes.py --run-dir evaluation\results\run-你的完整运行 --target evaluation\results\你的新报告
.\.venv\Scripts\python.exe scripts\compare_github_readmes.py --baseline evaluation\results\github-readmes-2026-10-07 --current evaluation\results\你的新报告 --dev evaluation\results\run-你的开发集运行
```

比较脚本要求开发集与完整运行的实现哈希一致，并核对分块、语料、模型和预算。预算重放直接使用基线保存的候选顺序，未重新调用向量模型；不是新的检索性能测量。

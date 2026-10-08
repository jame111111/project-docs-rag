"""复制一次已完成运行并据真实结果生成报告；不重新检索、不调参。"""
import argparse
import csv
import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text('utf-8'))


def percentage(value):
    return f'{value * 100:.2f}%'


def report(run_dir, target):
    run_dir, target = run_dir.resolve(), target.resolve()
    if not run_dir.is_relative_to(ROOT / 'evaluation/results') or not target.is_relative_to(ROOT / 'evaluation/results'):
        raise ValueError('报告路径必须位于本项目 evaluation/results')
    completion = load(run_dir / 'completion.json')
    if completion['status'] != 'completed' or completion['projects'] != 20 or completion['questions'] != 600:
        raise ValueError('只为已完成20项目600题的运行生成交付报告')
    if target.exists():
        raise ValueError('交付目录已存在，不覆盖历史报告；指定新目录')
    shutil.copytree(run_dir, target)
    aggregate = load(target / 'summary.json')
    regression = aggregate['metadata'].get('evaluation_purpose') == 'regression_seen_questions'
    sources = {s['id']: s for s in load(ROOT / 'evaluation/github_readmes/sources.json')['sources']}
    checks = load(target / 'project_checks.json')
    with (target / 'per_project_summary.csv').open(encoding='utf-8-sig', newline='') as file:
        per_project = list(csv.DictReader(file))
    lines = ['# 20 个 GitHub README 的 600 题测试', '',
        '运行日期：2026-10-07。结果来自真实 CPU BGE/Chroma/BM25 检索，不是离线假向量。', '',
        f'20 份独立 README、600 道中文题（480 道有依据、120 道无依据），共 {completion["retrieval_comparisons"]} 条三模式/双 top_k 对照。',
        f'实际索引合计 {sum(c["parents"] for c in checks)} 个父块、{sum(c["children"] for c in checks)} 个子块；各项目只有一份文档，未混合检索20个仓库。', '',
        '**完整证据覆盖率不是回答准确率。当前没有生成模型配置，600 条默认模式生成记录全部未运行。参考答案与负例的独立人工复核尚未完成。**', '',
        '正例由240个不同事实各两种措辞组成，不是480个独立事实。事实组未跨原开发/最终集；开发集440题、原最终集160题。' +
        ('这批题在基线测试中已经查看。本轮先运行开发集，再冻结代码运行全部题，属于回归测试；不能作为未见过的最终验证。' if regression else
         '快照、题集与代码哈希在首次检索前冻结，本次没有围绕最终题调参。'), '',
        '## 全部题的检索对照', '', '| top_k | 模式 | 完整覆盖/480 | 覆盖率 | 平均上下文字符 | 检索中位数 ms |',
        '|---:|---|---:|---:|---:|---:|']
    labels = {'vector_child': '纯向量子块', 'hybrid_child': '混合检索子块', 'hybrid_parent': '混合检索父块'}
    for row in aggregate['summary']:
        if row['split'] == 'all' and row['kind'] == 'all':
            lines.append(f'| {row["top_k"]} | {labels[row["mode"]]} | {row["covered"]} | {percentage(row["complete_evidence_coverage"])} | {row["mean_context_chars"]} | {row["median_retrieval_ms"]} |')
    lines += ['', '字符均值和耗时包含全部题；覆盖率分母只含正例。120个无依据问题的拒答质量不能用检索命中来衡量。耗时为模型预热后单次测量，共享同题候选，不包含模型生成或源码构建，不作为生产性能承诺。', '',
        ('## 开发/原最终集回归（top_k=5）' if regression else '## 开发/最终集（top_k=5）'), '', '| 题集 | 正例数 | 纯向量子块 | 混合检索子块 | 混合检索父块 |', '|---|---:|---:|---:|---:|']
    for split in ['dev', 'final']:
        subset = {r['mode']: r for r in aggregate['summary'] if r['split'] == split and r['kind'] == 'all' and r['top_k'] == 5}
        lines.append('| ' + split + ' | ' + str(subset['vector_child']['answerable']) + ' | ' + ' | '.join(percentage(subset[mode]['complete_evidence_coverage']) for mode in labels) + ' |')
    lines += ['', '## 两种问法（top_k=5）', '', '| 问法 | 正例数 | 纯向量子块 | 混合检索子块 | 混合检索父块 |', '|---|---:|---:|---:|---:|']
    for kind in ['direct', 'colloquial']:
        subset = {r['mode']: r for r in aggregate['summary'] if r['split'] == 'all' and r['kind'] == kind and r['top_k'] == 5}
        lines.append('| ' + kind + ' | 240 | ' + ' | '.join(percentage(subset[mode]['complete_evidence_coverage']) for mode in labels) + ' |')
    lines += ['', '这组口语改述的结果没有整体下降，但只说明这些固定问法的结果，不能外推到所有口语问题。当前使用中文向量模型检索英文原文，BM25对中文词与英文术语的映射有限，未加入翻译或问题改写。', '',
        '## 逐项目（top_k=5，每项目24道正例）', '', '| 项目及快照来源 | 纯向量子块 | 混合检索子块 | 混合检索父块 |', '|---|---:|---:|---:|---:|']
    for check in checks:
        pid = check['project']
        subset = {r['mode']: r for r in per_project if r['project'] == pid and r['split'] == 'all' and r['kind'] == 'all' and r['top_k'] == '5'}
        source = sources[pid]
        lines.append(f'| [{source["repository"]}]({source["source_url"]}) | ' + ' | '.join(f'{r["covered"]}/24 ({percentage(float(r["complete_evidence_coverage"]))})' for mode in labels for r in [subset[mode]]) + ' |')
    counts, empty = Counter(), Counter()
    parent_regression = None
    for check in checks:
        pid = check['project']
        rows = load(target / pid / 'retrieval.json')['results']
        by_question = {}
        for row in rows:
            if row['top_k'] == 5 and row['answerable']:
                by_question.setdefault(row['id'], {})[row['mode']] = row
        for qid, modes in by_question.items():
            a, b, c = [modes[mode]['complete_evidence_covered'] for mode in labels]
            counts.update({'hybrid_gain': b and not a, 'hybrid_loss': a and not b,
                'parent_gain': c and not b, 'parent_loss': b and not c, 'parent_miss': not c})
            empty.update({mode: not row['context'] for mode, row in modes.items()})
            if not parent_regression and modes['hybrid_child']['split'] == 'dev' and b and not c and not modes['hybrid_parent']['context']:
                dataset = load(ROOT / 'evaluation/github_readmes/projects' / pid / 'evaluation/dataset.json')
                q = next(q for q in dataset['questions'] if q['id'] == qid)
                parent_regression = {'project': pid, 'question': q, 'modes': modes, 'category': 'parent_budget_regression',
                    'answer': {'run_status': 'not_run', 'reason': 'model_not_configured', 'review': 'unverified', 'answer': '', 'citations': []}}
    cases = load(target / 'cases.json')
    if parent_regression:
        cases = [parent_regression if case['category'] == 'regression' else case for case in cases]
        (target / 'cases.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2), 'utf-8')
    lines += ['', '## 观察到的改善与失败', '',
        f'- 混合检索相对纯向量：改善 {counts["hybrid_gain"]} 题、退步 {counts["hybrid_loss"]} 题，净变化 {counts["hybrid_gain"] - counts["hybrid_loss"]:+d} 题。不能只展示有利案例。',
        f'- 父块相对混合子块：改善 {counts["parent_gain"]} 题、退步 {counts["parent_loss"]} 题；仍有 {counts["parent_miss"]} 道正例未完整覆盖。增益来自补充同章节上下文，同时增加上下文字符。',
        f'- 正例中父块模式有 {empty["hybrid_parent"]} 题上下文为空。' +
        ('本轮跳过超预算完整块后继续检查后面的命中，但不截断、不扩充 top_k。若所有命中父块都过长，仍不能提供完整上下文。' if regression else
         '超预算首块会连同后续块舍弃。长列表、HTML表格及较长不可拆单元会放大这一限制。没有在看到最终结果后改分块或预算。'),
        '- Argo CD 与 OpenSearch 等概览 README 存在父块退步；项目复杂不等于 README 内容充足。链接入口题只能回答去哪里查，不能生成链接内的配置步骤。',
        '- 单项目索引结果不验证多个仓库混库时的跨项目误检。引用位置与父子关系已自动核对，语义正确性仍需要独立人工判断。', '',
        '逐题完整候选与上下文在各项目 `retrieval.json`；代表案例见 [cases.md](cases.md)。', '',
        '## 生成与工程验证', '',
        '600条生成记录：`not_run / model_not_configured`；答案与引用为空，`review=unverified`。不自动给无依据问题打正确拒答分。人工表见 [answers-review.csv](answers-review.csv)，当前没有可以公布的回答准确率或拒答率。', '',
        '工程检查记录见 [verification.json](../../../docs/project-docs/verification.json)。离线测试替身不参与本报告的真实检索数据。20个实际索引均核对父子归属、真实正文偏移和SQLite/Chroma数量。', '',
        '源码与固定资料的复现命令见 [测试说明](../../github_readmes/README.md)。本报告未验证20个上游软件自身的构建和部署，也未执行其 README 命令。']
    (target / 'REPORT.md').write_text('\n'.join(lines) + '\n', 'utf-8')
    case_lines = ['# 实际代表案例', '', '下列案例来自开发题。所有模型答案均未运行，不能把参考答案当作模型输出。' +
                  ('本轮使用已经查看过的固定题作回归，不作为新题泛化证明。' if regression else '没有围绕最终题调整配置。'), '']
    for case in cases:
        q = case['question']
        case_lines += [f'## {q["id"]}：{case["category"]}', '', q['question'], '', '**参考答案要点（待人工独立复核）**：' + '；'.join(q['reference_points']), '', '**必需原文证据**：']
        for e in q['evidence']:
            case_lines += [f'- {e["doc_id"]} / {e["section"]} / [{e["start"]}, {e["end"]})', '', '````text', e['quote'], '````', '']
        for mode, row in case['modes'].items():
            case_lines += [f'### {labels[mode]}：完整覆盖={row["complete_evidence_covered"]}，字符={row["context_chars"]}', '', '````text', ''.join(c['formatted'] for c in row['context']) or '（实际上下文为空）', '````', '']
        case_lines += ['模型答案：未运行（缺少配置）；引用：未生成；回答正确性：未验证。', '']
    (target / 'cases.md').write_text('\n'.join(case_lines), 'utf-8')
    (target / 'observations.json').write_text(json.dumps({'top_k': 5, 'positive_question_changes': counts,
            'empty_positive_contexts': empty, 'source_run': run_dir.name}, ensure_ascii=False, indent=2), 'utf-8')
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--target', type=Path, default=ROOT / 'evaluation/results/github-readmes-2026-10-07')
    args = parser.parse_args()
    report(args.run_dir, args.target)

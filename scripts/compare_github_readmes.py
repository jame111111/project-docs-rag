"""比较两轮真实结果，并用冻结候选单独重放预算修复；不调用模型或伪造答案。"""
import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

from app.chunking import chunk_document
from app.documents import read_markdown
from app.retrieval import build_context
from evaluation.common import MODES, evidence_covered, write_csv, write_json
from evaluation.github_readme_eval import summarize

LABELS = dict(zip(MODES, ['纯向量子块', '混合检索子块', '混合检索父块']))


def load(path):
    return json.loads(path.read_text('utf-8'))


class SnapshotStore:
    """从固定正文重建同一批块，仅用于冻结候选的上下文重放，不建立向量索引。"""
    def __init__(self, fixture):
        manifest = load(fixture / 'corpus/manifest.json')
        self.docs, self.parents, self.children = [], [], []
        for doc in manifest['documents']:
            path = fixture / 'corpus' / doc['snapshot_file']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == doc['sha256']
            body, _ = read_markdown(path)
            self.docs.append({**doc, 'body': body})
            parents, children = chunk_document(doc['id'], body)
            self.parents.extend(asdict(p) for p in parents)
            self.children.extend(asdict(c) for c in children)

    def documents(self):
        return self.docs

    def chunks(self, kind):
        return self.parents if kind == 'parent' else self.children


def row_key(row):
    return row['id'], row['mode'], row['top_k']


def coverage_table(summaries, split='all'):
    return {(r['mode'], r['top_k']): r for r in summaries
            if r['split'] == split and r['kind'] == 'all'}


def compare(baseline, current, dev):
    old_meta, new_meta, dev_meta = [load(p / 'metadata.json') for p in [baseline, current, dev]]
    # 不可在查看全部回归题后继续调算法，然后宣称开发阶段已经冻结。
    assert dev_meta['split'] == 'dev' and dev_meta['phase'] == 'retrieval'
    assert new_meta['code_sha256'] == dev_meta['code_sha256']
    assert old_meta['code_sha256']['backend/app/chunking.py'] == new_meta['code_sha256']['backend/app/chunking.py']
    assert old_meta['embedding_model'] == new_meta['embedding_model']
    assert old_meta['embedding_revision'] == new_meta['embedding_revision']
    for key in ['context_budget', 'candidates_per_route', 'rrf_k', 'top_k']:
        assert old_meta[key] == new_meta[key]
    for path in [baseline, current]:
        assert load(path / 'completion.json')['retrieval_comparisons'] == 3600
    selected = load(ROOT / 'evaluation/github_readmes/selection.json')['projects']
    old_rows, new_rows, replay_rows, cases = [], [], [], []
    candidate_rank_changes = 0
    counts = {mode: {'gained': 0, 'lost': 0} for mode in MODES}
    empty = {'baseline': 0, 'current': 0, 'budget_only': 0}
    hybrid_gain, hybrid_loss = [], []
    for project in selected:
        pid = project['id']
        fixture = ROOT / 'evaluation/github_readmes/projects' / pid
        questions = {q['id']: q for q in load(fixture / 'evaluation/dataset.json')['questions']}
        old = load(baseline / pid / 'retrieval.json')['results']
        new = load(current / pid / 'retrieval.json')['results']
        assert {row_key(r) for r in old} == {row_key(r) for r in new}
        old_by_key, new_by_key = [{row_key(r): r for r in rows} for rows in [old, new]]
        store = SnapshotStore(fixture)
        for row in old:
            q = questions[row['id']]
            assert row['question'] == q['question'] == new_by_key[row_key(row)]['question']
            context, chars = build_context(store, row['selected_child_ids'], row['mode'], old_meta['context_budget'])
            covered = all(evidence_covered(e, context) for e in q['evidence']) if q['answerable'] else None
            replay_rows.append({**{k: row[k] for k in ['project', 'id', 'question', 'kind', 'fact_group', 'split', 'answerable', 'mode', 'top_k']},
                'context': context, 'context_chars': chars, 'complete_evidence_covered': covered,
                'selected_child_ids': row['selected_child_ids']})
        for qid, q in questions.items():
            a = old_by_key[qid, 'vector_child', 5]
            b = new_by_key[qid, 'vector_child', 5]
            candidate_rank_changes += a['diagnostics']['vector_ids'] != b['diagnostics']['vector_ids']
            if not q['answerable']:
                continue
            a_modes = {m: old_by_key[qid, m, 5] for m in MODES}
            b_modes = {m: new_by_key[qid, m, 5] for m in MODES}
            for mode in MODES:
                before, after = a_modes[mode]['complete_evidence_covered'], b_modes[mode]['complete_evidence_covered']
                counts[mode]['gained'] += after and not before
                counts[mode]['lost'] += before and not after
            empty['baseline'] += not a_modes['hybrid_parent']['context']
            empty['current'] += not b_modes['hybrid_parent']['context']
            case = {'project': pid, 'question': q, 'baseline': a_modes, 'current': b_modes,
                    'answer': {'run_status': 'not_run', 'reason': 'model_not_configured', 'review': 'unverified', 'answer': '', 'citations': []}}
            if qid == 'spark-Q07':
                cases.append({**case, 'category': '预算修复：前置大块不再阻止后续命令'})
            if q['split'] == 'dev':
                before, after = [r['hybrid_child']['complete_evidence_covered'] for r in [a_modes, b_modes]]
                if after and not before: hybrid_gain.append(case)
                if before and not after: hybrid_loss.append(case)
        old_rows.extend(old)
        new_rows.extend(new)
    for category, candidates in [('混合子块改善', hybrid_gain), ('混合子块仍有退步', hybrid_loss)]:
        if candidates:
            cases.append({**candidates[0], 'category': category})
    empty['budget_only'] = sum(not r['context'] for r in replay_rows
        if r['answerable'] and r['mode'] == 'hybrid_parent' and r['top_k'] == 5)
    # 重放没有测量检索延迟，禁止将零值或缓存耗时当作性能提升。
    replay_compact = [{k: v for k, v in r.items() if k not in ['context', 'selected_child_ids']} for r in replay_rows]
    replay_summary = summarize([{**r, 'retrieval_ms': 0} for r in replay_compact])
    for row in replay_summary:
        row.pop('median_retrieval_ms')
    write_json(current / 'budget-ablation.json', {'method': '基线实际候选和顺序不变，仅用同一正文/父子块重放跳过超预算完整块的策略；未调用检索或生成模型。',
        'baseline': baseline.name, 'chunking_sha256': new_meta['code_sha256']['backend/app/chunking.py'],
        'summary': replay_summary, 'results': replay_rows})
    write_csv(current / 'budget-ablation.csv', replay_compact)
    write_json(current / 'development-check.json', {'source_run': dev.name, 'metadata': dev_meta,
        'summary': load(dev / 'summary.json')['summary'],
        'retrieval_csv_sha256': hashlib.sha256((dev / 'retrieval.csv').read_bytes()).hexdigest()})
    (current / 'development-retrieval.csv').write_bytes((dev / 'retrieval.csv').read_bytes())
    old_summary, new_summary = [load(p / 'summary.json')['summary'] for p in [baseline, current]]
    data = {'baseline': baseline.name, 'current': current.name, 'development_run': dev.name,
        'question_changes': counts, 'empty_positive_parent_contexts': empty,
        'vector_candidate_rank_changed_questions': candidate_rank_changes,
        'baseline_summary': old_summary, 'current_summary': new_summary,
        'budget_only_summary': replay_summary, 'evaluation_purpose': 'regression_seen_questions',
        'fresh_holdout': 'unverified', 'answer_accuracy': 'unverified'}
    write_json(current / 'comparison.json', data)
    write_json(current / 'comparison-cases.json', cases)
    lines = ['# 测试后改进的回归对照', '',
        '这批题在基线测试中已查看。本轮先用440道开发题验证，冻结代码后运行全部600题；原 final 部分仅作回归，未见过的新题验证仍待完成。', '',
        '改动：跳过放不下的完整上下文块并继续检查剩余 top_k 命中；BM25 去除标点和常见虚词，保留技术标识符；索引指纹包含分词算法版本，旧索引启动时标记过期。没有改变文档、问题、子块、候选数、RRF k 或预算。', '',
        '## 全部480道正例', '', '| top_k | 模式 | 基线 | 当前 | 变化（百分点） |', '|---:|---|---:|---:|---:|']
    old_table, new_table = coverage_table(old_summary), coverage_table(new_summary)
    for top_k in [1, 5]:
        for mode in MODES:
            a, b = [t[mode, top_k]['covered'] for t in [old_table, new_table]]
            lines.append(f'| {top_k} | {LABELS[mode]} | {a}/480 ({a/480:.2%}) | {b}/480 ({b/480:.2%}) | {(b-a)/480*100:+.2f} |')
    lines += ['', '这是完整证据覆盖率，不能写成回答准确率。正例为240个事实各两种措辞，独立人工核对尚未完成。', '',
              '## 固定候选，只改变预算策略', '', '| top_k | 父块基线 | 仅预算修复 |', '|---:|---:|---:|']
    replay_table = coverage_table(replay_summary)
    for top_k in [1, 5]:
        a, b = [t['hybrid_parent', top_k]['covered'] for t in [old_table, replay_table]]
        lines.append(f'| {top_k} | {a}/480 | {b}/480 |')
    lines += ['', '重放使用基线保存的真实候选及顺序，从固定正文重建同一批父子块，没有重新检索。这一对照只观察上下文预算处理；完整新版另跑真实 BGE/Chroma/BM25。', '',
        f'两轮实际运行有 {candidate_rank_changes}/600 题的向量候选顺序变化（独立重建 Chroma 后的实测）；因此完整新版的差值包含运行差异，不能全归因于关键词清理。', '',
        f'默认 top_k=5 的空父块上下文：基线 {empty["baseline"]} 题，仅预算修复 {empty["budget_only"]} 题，当前 {empty["current"]} 题（均只统计正例）。不截断大块、不使用子块冒充父块、不扩充 top_k；全部命中都过长时仍会无上下文。', '',
        '## 改善和退步（top_k=5）', '', '| 模式 | 改善题数 | 退步题数 |', '|---|---:|---:|']
    for mode in MODES:
        lines.append(f'| {LABELS[mode]} | {counts[mode]["gained"]} | {counts[mode]["lost"]} |')
    lines += ['', '逐题三个代表案例见 [comparison-cases.md](comparison-cases.md)。全文档位置、预算及三模式结果见 [REPORT.md](REPORT.md)。', '',
        '仍存在的限制：中文问题与英文术语不一致、无相关内容的 README、前三个父块的取舍及不可拆的大表格。没有通过分词把所有口语问题翻译成文档术语。', '',
        '当前没有生成模型配置，600条生成记录未运行。引用合法性、原文偏移和离线故障流程已经验证；真实错误章节拒答、回答正确性和120道负例的拒答质量仍未验证。']
    (current / 'comparison.md').write_text('\n'.join(lines) + '\n', 'utf-8')
    lines = ['# 修改前后实际案例', '', '案例来自开发题。参考要点与模型答案分开；模型未配置，没有实际生成的答案或引用。', '']
    for case in cases:
        q = case['question']
        lines += [f'## {q["id"]}：{case["category"]}', '', q['question'], '',
                  '参考要点（待独立人工核对）：' + '；'.join(q['reference_points']), '', '必需原文：']
        for e in q['evidence']:
            lines += [f'- {e["section"]} [{e["start"]}, {e["end"]})', '', '````text', e['quote'], '````', '']
        for stage in ['baseline', 'current']:
            for mode in MODES:
                row = case[stage][mode]
                lines += [f'### {stage} / {LABELS[mode]}：覆盖={row["complete_evidence_covered"]}，字符={row["context_chars"]}', '',
                          '````text', ''.join(c['formatted'] for c in row['context']) or '（实际上下文为空）', '````', '']
        lines += ['实际模型答案：未运行；引用：未生成；答案正确性：未验证。', '']
    (current / 'comparison-cases.md').write_text('\n'.join(lines), 'utf-8')
    print(json.dumps({'changes': counts, 'empty_positive_parent_contexts': empty,
                      'vector_candidate_rank_changes': candidate_rank_changes}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--current', required=True, type=Path)
    parser.add_argument('--dev', required=True, type=Path)
    args = parser.parse_args()
    compare(args.baseline, args.current, args.dev)

"""按真实运行生成报告；案例只从开发集挑选，不使用最终题调参。"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.config import Settings
from app.storage import Store

NAMES = {'vector_child': '纯向量 + 子块', 'hybrid_child': '混合检索 + 子块', 'hybrid_parent': '混合检索 + 父块'}


def main():
    parser = argparse.ArgumentParser()
    for name in ['dev', 'final', 'answers', 'output']:
        parser.add_argument(name, type=Path)
    parser.add_argument('--config', type=Path, default=ROOT/'evaluation/fixtures/open-source/profile.json')
    parser.add_argument('--data-dir', type=Path, default=ROOT/'data/runtime/evaluation-open-source')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    settings = Settings(product_config=args.config, data_dir=args.data_dir)
    state = Store(settings.data_dir/'metadata.sqlite3').state()
    runs = {}
    for name in ['dev', 'final', 'answers']:
        source = getattr(args, name)
        shutil.copytree(source, args.output/name)
        runs[name] = json.loads((source/'results.json').read_text('utf-8'))
        if runs[name]['metadata']['product_id'] != settings.product.id:
            raise ValueError('结果与当前产品不一致')
    lines = [f'# {settings.product.name}固定语料检索对照\n\n',
             f"语料 {state['documents']} 篇 / {state['parents']} 父块 / {state['children']} 子块。使用真实 CPU BGE、Chroma 与 BM25。\n\n",
             '三模式共享子块和同题候选。每路 10 个候选，RRF k=60，最多 3 个父块，预算 4000 字符；报告 top_k=1/5。\n\n',
             f"开发集 {runs['dev']['metadata']['answerable_count']} 正例；最终集 {runs['final']['metadata']['answerable_count']} 正例。配置冻结后最终集运行一次。\n\n",
             '| 题集 | top_k | 模式 | 完整证据覆盖率 | 平均上下文字符 | 检索耗时中位数 ms |\n|---|---:|---|---:|---:|---:|\n']
    for split in ['dev', 'final']:
        for r in runs[split]['summary']:
            lines.append(f"| {split} | {r['top_k']} | {NAMES[r['mode']]} | {r['complete_evidence_coverage']*100:.2f}% | {r['mean_context_chars']} | {r['median_retrieval_ms']} |\n")
    lines += ['\n覆盖率要求全部冻结证据区间都被实际上下文包含，不是回答准确率；无依据题覆盖率记 N/A。平均字符包含无依据题。\n',
              '\n耗时为预热后单次检索测量，不含生成或模型加载，不能推断生产性能。父块增加上下文，也可能受数量和预算限制而漏掉其他证据；是否有收益以本次逐题结果为准。\n',
              f"\n逐题回答状态：已生成 {sum(r['run_status'] == 'generated' for r in runs['answers']['results'])}；未运行 {sum(r['run_status'] == 'not_run' for r in runs['answers']['results'])}；错误 {sum(r['run_status'] == 'error' for r in runs['answers']['results'])}。正确性与拒答质量需人工核对，未经核对仍为未验证。\n",
              '\n[三个实际案例及上下文](cases.md)；全部逐题 JSON/CSV 见 dev、final、answers 目录。\n']
    (args.output/'REPORT.md').write_text(''.join(lines), 'utf-8')
    rows = runs['dev']['results']
    groups = {}
    for row in rows:
        if row['answerable']:
            groups.setdefault((row['id'], row['top_k']), {})[row['mode']] = row
    selections = []
    def select(predicate, description):
        item = next(((key, group) for key, group in groups.items()
                     if key[0] not in [s[0][0] for s in selections] and predicate(group)), None)
        if item:
            selections.append((*item, description))
        return bool(item)
    select(lambda g: not g['vector_child']['complete_evidence_covered'] and g['hybrid_child']['complete_evidence_covered'], '混合检索补齐证据')
    select(lambda g: not g['hybrid_child']['complete_evidence_covered'] and g['hybrid_parent']['complete_evidence_covered'], '父块回补补齐证据')
    select(lambda g: g['hybrid_child']['complete_evidence_covered'] and not g['hybrid_parent']['complete_evidence_covered'], '父块回补覆盖下降')
    while len(selections) < 3:
        if not select(lambda g: g['hybrid_child']['complete_evidence_covered'] == g['hybrid_parent']['complete_evidence_covered'], '父块回补没有改善覆盖'):
            if not select(lambda g: True, '其余实际检索差异'):
                break
    dataset = json.loads(settings.product.dataset_path.read_text('utf-8'))
    questions = {q['id']: q for q in dataset['questions']}
    cases, case_lines = [], ['# 三个实际开发集案例\n\n模型答案未运行；下面是参考要点与真实检索上下文，不能当作生成结果。\n']
    for (qid, top_k), group, description in selections:
        q = questions[qid]
        generated = [r for r in runs['answers']['results'] if r['id'] == qid and r['top_k'] == top_k]
        cases.append({'question': q, 'top_k': top_k, 'description': description, 'modes': group, 'generated_answers': generated})
        case_lines.append(f"\n## {qid}：{description}\n\n问题：{q['question']}（top_k={top_k}）\n\n参考要点：" + '；'.join(q['reference_points']) + '\n')
        for mode, row in group.items():
            answer = next((r for r in generated if r['mode'] == mode), None)
            answer_text = answer.get('answer') if answer and answer['run_status'] == 'generated' else '未运行或生成失败（见 answers 逐题状态）'
            case_lines.append(f"\n### {NAMES[mode]}\n\n完整覆盖：{row['complete_evidence_covered']}；上下文：{row['context_chars']} 字符；模型答案：{answer_text}\n")
            for block in row['context']:
                case_lines.append(f"\n**[{block['ref']}] {block['title']} / {block['section']}**\n\n`````markdown\n{block['text']}\n`````\n")
    (args.output/'cases.md').write_text(''.join(case_lines), 'utf-8')
    (args.output/'cases.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2), 'utf-8')
    print(args.output)


if __name__ == '__main__':
    main()

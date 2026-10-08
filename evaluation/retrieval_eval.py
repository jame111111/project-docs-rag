"""无生成模型调用。三模式 × top_k 1/5，共享同题候选，冻结配置。"""
import argparse
import statistics
from pathlib import Path
from time import perf_counter

from app.retrieval import build_context
from .common import MODES, evidence_covered, output_dir, setup, write_csv, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['dev', 'final', 'all'], default='dev')
    parser.add_argument('--config', type=Path, help='独立测试资料配置，不影响默认应用')
    parser.add_argument('--data-dir', type=Path, help='独立评测运行目录')
    args = parser.parse_args()
    settings, store, manager, retriever, questions, meta = setup(args.split, args.config, args.data_dir)
    started = perf_counter()
    manager.embeddings.encode(['模型预热'], query=True)
    meta['warmup_seconds'] = round(perf_counter() - started, 3)
    rows, compact = [], []
    for q in questions:
        candidates = retriever.candidates(q['question'])
        for top_k in [1, 5]:
            for mode in MODES:
                started = perf_counter()
                ids = (candidates['vector_ids'] if mode == 'vector_child' else candidates['fused_ids'])[:top_k]
                context, chars = build_context(store, ids, mode, settings.context_budget)
                covered = all(evidence_covered(e, context) for e in q['evidence']) if q['answerable'] else None
                context_ms = (perf_counter() - started) * 1000
                elapsed = candidates['vector_ms'] + (candidates['keyword_ms'] if mode != 'vector_child' else 0) + context_ms
                row = {'id': q['id'], 'question': q['question'], 'split': q['split'], 'answerable': q['answerable'],
                    'mode': mode, 'top_k': top_k, 'complete_evidence_covered': covered,
                    'context_chars': chars, 'retrieval_ms': round(elapsed, 3), 'context': context,
                    'selected_child_ids': ids, 'diagnostics': candidates}
                rows.append(row)
                compact.append({k: v for k, v in row.items() if k not in ['context', 'diagnostics', 'selected_child_ids']})
    summary = []
    for top_k in [1, 5]:
        for mode in MODES:
            subset = [r for r in rows if r['mode'] == mode and r['top_k'] == top_k]
            positives = [r for r in subset if r['answerable']]
            summary.append({'mode': mode, 'top_k': top_k, 'answerable_count': len(positives),
                'complete_evidence_coverage': round(sum(r['complete_evidence_covered'] for r in positives)/len(positives), 4) if positives else None,
                'mean_context_chars': round(statistics.mean(r['context_chars'] for r in subset), 1),
                'median_retrieval_ms': round(statistics.median(r['retrieval_ms'] for r in subset), 2),
                'negative_coverage': 'not_applicable', 'answer_accuracy': 'unverified'})
    meta['timing_method'] = '预热后单次测量；同题向量/BM25候选共享，报告对应路耗时加上下文组织耗时，不是生成耗时或基准性能承诺。'
    out = output_dir('retrieval')
    write_json(out/'results.json', {'metadata': meta, 'summary': summary, 'results': rows})
    write_csv(out/'results.csv', compact)
    write_csv(out/'summary.csv', summary)
    print(out)
    for row in summary:
        print(row)


if __name__ == '__main__':
    main()

"""20个项目独立索引、每个README30题。复用真实CPU模型，复用应用检索与引用逻辑。"""
import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from time import perf_counter

from app.answering import LLMClient, LLMError, answer_question
from app.config import ROOT, Settings
from app.indexing import Embeddings, INDEX_VERSION
from app.retrieval import build_context
from .common import MODES, evidence_covered, output_dir, setup, write_csv, write_json

SUITE = ROOT / 'evaluation/github_readmes'


def summarize(rows, project='all'):
    summaries = []
    for split in ['all', 'dev', 'final']:
        for kind in ['all', 'direct', 'colloquial']:
            for top_k in [1, 5]:
                for mode in MODES:
                    subset = [r for r in rows if r['mode'] == mode and r['top_k'] == top_k
                              and (split == 'all' or r['split'] == split)
                              and (kind == 'all' or r['kind'] == kind)]
                    if not subset:
                        continue
                    positives = [r for r in subset if r['answerable']]
                    summaries.append({'project': project, 'split': split, 'kind': kind,
                        'mode': mode, 'top_k': top_k, 'questions': len(subset), 'answerable': len(positives),
                        'covered': sum(r['complete_evidence_covered'] for r in positives),
                        'complete_evidence_coverage': round(sum(r['complete_evidence_covered'] for r in positives) / len(positives), 4) if positives else None,
                        'mean_context_chars': round(statistics.mean(r['context_chars'] for r in subset), 1),
                        'median_retrieval_ms': round(statistics.median(r['retrieval_ms'] for r in subset), 3),
                        'unsupported_answer_quality': 'unverified', 'answer_accuracy': 'unverified'})
    return summaries


def verify_index(store, manager):
    state = manager.ensure_ready()
    docs = {d['id']: d for d in store.documents()}
    parents = {p['id']: p for p in store.chunks('parent')}
    children = store.chunks('child')
    for block in [*parents.values(), *children]:
        if docs[block['doc_id']]['body'][block['start']:block['end']] != block['text']:
            raise ValueError('正文偏移与真实文本不一致')
    for child in children:
        parent = parents[child['parent_id']]
        if child['doc_id'] != parent['doc_id'] or not parent['start'] <= child['start'] < child['end'] <= parent['end']:
            raise ValueError('子块越过父块或文档边界')
    if manager.collection.count() != len(children) or state['documents'] != 1:
        raise ValueError('SQLite/Chroma索引数量不一致或存在其他README')
    return {k: state[k] for k in ['documents', 'parents', 'children', 'fingerprint']}


def make_answer(q, retriever, settings):
    row = {'id': q['id'], 'question': q['question'], 'answerable': q['answerable'], 'split': q['split'],
           'mode': 'hybrid_parent', 'top_k': 5, 'reference_points': q['reference_points'],
           'evidence': q['evidence'], 'review': 'unverified', 'review_notes': ''}
    if not settings.llm_configured:
        row.update(run_status='not_run', reason='model_not_configured', answer='', citations=[])
    else:
        try:
            result = answer_question(q['question'], retriever, LLMClient(settings))
            row.update(run_status='generated', **result)
        except LLMError as exc:
            row.update(run_status='error', reason=str(exc), answer='', citations=[])
        except Exception as exc:
            row.update(run_status='error', reason=type(exc).__name__, answer='', citations=[])
    return row


def run(phase='all', split='all', runtime_root=None):
    selected = json.loads((SUITE / 'selection.json').read_text('utf-8'))['projects']
    inventory = json.loads((SUITE / 'datasets.json').read_text('utf-8'))
    hashes = {item['project']: item['dataset_sha256'] for item in inventory}
    # 先核对全套题集再跑，最终题与配置在第一次检索前已冻结。
    for project in selected:
        path = SUITE / 'projects' / project['id'] / 'evaluation/dataset.json'
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[project['id']]:
            raise ValueError('题集发生变化，必须明确建立新的测试快照')
    base_settings = Settings()
    runtime_root = Path(runtime_root) if runtime_root else ROOT / 'data/runtime/github-readmes-v2'
    embeddings = Embeddings(base_settings)
    started = perf_counter()
    embeddings.encode(['模型预热'], query=True)
    warmup_seconds = round(perf_counter() - started, 3)
    out = output_dir('github-readmes')
    metadata = {'suite': '20-github-readmes', 'phase': phase, 'split': split,
        'project_count': len(selected), 'embedding_model': base_settings.embedding_model,
        'embedding_revision': base_settings.embedding_revision, 'device': base_settings.embedding_device,
        'llm_model': base_settings.llm_model if base_settings.llm_configured else 'not_configured',
        'context_budget': base_settings.context_budget, 'candidates_per_route': 10, 'rrf_k': 60,
        'top_k': [1, 5], 'warmup_seconds': warmup_seconds,
        'index_version': INDEX_VERSION,
        'evaluation_purpose': 'regression_seen_questions',
        'dataset_inventory_sha256': hashlib.sha256((SUITE / 'datasets.json').read_bytes()).hexdigest(),
        'code_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
            ['backend/app/chunking.py', 'backend/app/retrieval.py', 'backend/app/indexing.py', 'backend/app/answering.py']},
        'timing_method': 'CPU模型预热；每题候选共享，各模式计算对应路耗时加上下文组织耗时；不含生成耗时，不作生产性能承诺。',
        'limitations': ['中文问题对英文原文', '每组正例有两种措辞，只有240组不同事实',
                        '独立项目索引，不是20个仓库混合检索', '参考答案与负例的独立人工复核待完成',
                        '题目已在基线测试中查看；本次为回归测试，非未见过的最终验证',
                        '无模型或未人工核对时，回答准确率与拒答质量未验证']}
    write_json(out / 'metadata.json', metadata)
    compact, project_summary, answer_rows, statuses = [], [], [], []
    case_candidates = {'hybrid_gain': [], 'parent_gain': [], 'regression': [], 'miss': []}
    print(out, flush=True)
    for project in selected:
        pid = project['id']
        directory = SUITE / 'projects' / pid
        settings, store, manager, retriever, questions, meta = setup(split, directory / 'profile.json',
                runtime_root / pid, embeddings=embeddings)
        index = verify_index(store, manager)
        meta.update(project=pid, repository=project['repository'], index=index)
        project_out = out / pid
        project_out.mkdir()
        rows, answers = [], []
        if phase in ['all', 'retrieval']:
            for q in questions:
                candidates = retriever.candidates(q['question'])
                per_question = []
                for top_k in [1, 5]:
                    for mode in MODES:
                        started = perf_counter()
                        ids = (candidates['vector_ids'] if mode == 'vector_child' else candidates['fused_ids'])[:top_k]
                        context_skipped = []
                        context, chars = build_context(store, ids, mode, settings.context_budget, context_skipped)
                        covered = all(evidence_covered(e, context) for e in q['evidence']) if q['answerable'] else None
                        ms = candidates['vector_ms'] + (candidates['keyword_ms'] if mode != 'vector_child' else 0) + (perf_counter() - started) * 1000
                        row = {'project': pid, 'id': q['id'], 'question': q['question'], 'kind': q['kind'],
                            'fact_group': q['fact_group'], 'split': q['split'], 'answerable': q['answerable'],
                            'mode': mode, 'top_k': top_k, 'complete_evidence_covered': covered,
                            'context_chars': chars, 'retrieval_ms': round(ms, 3), 'context': context,
                            'selected_child_ids': ids, 'diagnostics': {**candidates, 'context_skipped': context_skipped}}
                        rows.append(row)
                        per_question.append(row)
                        compact.append({k: v for k, v in row.items() if k not in ['context', 'diagnostics', 'selected_child_ids']})
                if q['answerable'] and q['split'] == 'dev':
                    modes = {r['mode']: r for r in per_question if r['top_k'] == 5}
                    vector, hybrid, parent = [modes[m]['complete_evidence_covered'] for m in MODES]
                    categories = []
                    if hybrid and not vector: categories.append('hybrid_gain')
                    if parent and not hybrid: categories.append('parent_gain')
                    if (hybrid and not parent) or (vector and not hybrid): categories.append('regression')
                    if not parent: categories.append('miss')
                    for category in categories:
                        if len(case_candidates[category]) < 3:
                            case_candidates[category].append({'project': pid, 'question': q, 'modes': modes})
        if phase in ['all', 'answers']:
            for q in questions:
                row = make_answer(q, retriever, settings)
                row['project'] = pid
                answers.append(row)
                answer_rows.append(row)
                write_json(project_out / 'answers.json', {'metadata': meta, 'results': answers, 'answer_accuracy': 'unverified'})
        if rows:
            summary = summarize(rows, pid)
            project_summary.extend(summary)
            write_json(project_out / 'retrieval.json', {'metadata': meta, 'summary': summary, 'results': rows})
        status = {'project': pid, **index, 'questions': len(questions), 'question_evidence_positions': 'passed',
                  'parent_child_offsets': 'passed', 'sqlite_chroma_count': 'passed',
                  'retrieval_rows': len(rows), 'answer_statuses': dict(Counter(a['run_status'] for a in answers))}
        statuses.append(status)
        write_json(out / 'project_checks.json', statuses)
        write_csv(out / 'retrieval.csv', compact)
        write_csv(out / 'per_project_summary.csv', project_summary)
        write_csv(out / 'answers-review.csv', [{k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v
            for k, v in r.items() if k not in ['evidence', 'timings']} for r in answer_rows])
        print(pid, 'questions', len(questions), 'parents', index['parents'], 'children', index['children'],
              'retrieval', len(rows), 'answers', status['answer_statuses'], flush=True)
    overall = summarize(compact)
    write_json(out / 'summary.json', {'metadata': metadata, 'summary': overall,
         'answer_statuses': dict(Counter(r['run_status'] for r in answer_rows)),
         'answer_accuracy': 'unverified', 'false_refusal_rate': 'unverified', 'correct_refusal_rate': 'unverified'})
    write_csv(out / 'summary.csv', overall)
    cases, seen = [], set()
    for category in ['hybrid_gain', 'parent_gain', 'regression', 'miss']:
        for case in case_candidates[category]:
            if case['question']['id'] in seen:
                continue
            seen.add(case['question']['id'])
            answer = next((r for r in answer_rows if r['id'] == case['question']['id']),
                          {'run_status': 'not_run', 'reason': 'retrieval_only', 'review': 'unverified', 'answer': ''})
            cases.append({**case, 'category': category, 'answer': answer})
            break
    write_json(out / 'cases.json', cases)
    write_json(out / 'completion.json', {'status': 'completed', 'projects': len(statuses),
        'questions': sum(s['questions'] for s in statuses), 'retrieval_comparisons': len(compact),
        'answer_records': len(answer_rows), 'model_configured': base_settings.llm_configured})
    print('completed', out, flush=True)
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['all', 'retrieval', 'answers'], default='all')
    parser.add_argument('--split', choices=['all', 'dev', 'final'], default='all')
    parser.add_argument('--runtime-root', type=Path, help='独立测试索引目录，默认使用 github-readmes-v2，保留旧基线索引')
    args = parser.parse_args()
    run(args.phase, args.split, args.runtime_root)

"""核对600题/3600条实际结果、完整上下文与原文偏移；不重跑检索。"""
import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
from app.documents import read_markdown
from evaluation.common import evidence_covered


def verify(directory):
    completion = json.loads((directory / 'completion.json').read_text('utf-8'))
    assert completion['projects'] == 20 and completion['questions'] == 600
    assert completion['retrieval_comparisons'] == 3600 and completion['answer_records'] == 600
    inventory = json.loads((ROOT / 'evaluation/github_readmes/datasets.json').read_text('utf-8'))
    count = 0
    totals = Counter()
    for item in inventory:
        pid = item['project']
        fixture = ROOT / 'evaluation/github_readmes/projects' / pid
        dataset_path = fixture / 'evaluation/dataset.json'
        assert hashlib.sha256(dataset_path.read_bytes()).hexdigest() == item['dataset_sha256']
        questions = {q['id']: q for q in json.loads(dataset_path.read_text('utf-8'))['questions']}
        body, _ = read_markdown(fixture / 'corpus/README.md')
        result = json.loads((directory / pid / 'retrieval.json').read_text('utf-8'))
        run_dataset_path = directory / pid / 'dataset-at-run.json'
        original = json.loads(run_dataset_path.read_text('utf-8')) if run_dataset_path.exists() else json.loads(dataset_path.read_text('utf-8'))
        assert result['metadata']['dataset_sha256'] == hashlib.sha256((run_dataset_path if run_dataset_path.exists() else dataset_path).read_bytes()).hexdigest()
        # 允许修正展示章节名，问题、答案要点、分组、证据原文与区间必须仍与运行时相同。
        for original_q in original['questions']:
            current_q = questions[original_q['id']]
            for key in ['question', 'reference_points', 'answerable', 'split', 'kind', 'fact_group']:
                assert original_q[key] == current_q[key]
            assert [{k: v for k, v in e.items() if k != 'section'} for e in original_q['evidence']] == [{k: v for k, v in e.items() if k != 'section'} for e in current_q['evidence']]
        rows = result['results']
        assert len(rows) == 180
        seen = set()
        for row in rows:
            key = (row['id'], row['mode'], row['top_k'])
            assert key not in seen
            seen.add(key)
            q = questions[row['id']]
            assert row['question'] == q['question']
            assert row['answerable'] == q['answerable']
            context = row['context']
            assert row['context_chars'] == sum(len(c['formatted']) for c in context) <= 4000
            assert len({c['id'] for c in context}) == len(context)
            if row['mode'] == 'hybrid_parent':
                assert len(context) <= 3
            for ref, block in enumerate(context, start=1):
                assert block['doc_id'] == 'readme-' + pid + '-doc'
                assert body[block['start']:block['end']] == block['text']
                assert block['ref'] == ref
            covered = all(evidence_covered(e, context) for e in q['evidence']) if q['answerable'] else None
            assert row['complete_evidence_covered'] == covered
            if row['top_k'] == 5 and q['answerable']:
                totals[row['mode']] += bool(covered)
            count += 1
        answers = json.loads((directory / pid / 'answers.json').read_text('utf-8'))['results']
        assert len(answers) == 30
        if not completion['model_configured']:
            assert all(a['run_status'] == 'not_run' and a['reason'] == 'model_not_configured'
                and not a['answer'] and not a['citations'] and a['review'] == 'unverified' for a in answers)
    with (directory / 'answers-review.csv').open(encoding='utf-8-sig', newline='') as file:
        assert len(list(csv.DictReader(file))) == 600
    assert count == 3600
    if (directory / 'comparison.json').exists():
        comparison = json.loads((directory / 'comparison.json').read_text('utf-8'))
        baseline = directory.parent / comparison['baseline']
        ablation = json.loads((directory / 'budget-ablation.json').read_text('utf-8'))
        development = json.loads((directory / 'development-check.json').read_text('utf-8'))
        current_meta = json.loads((directory / 'metadata.json').read_text('utf-8'))
        assert development['metadata']['code_sha256'] == current_meta['code_sha256']
        assert ablation['chunking_sha256'] == current_meta['code_sha256']['backend/app/chunking.py']
        assert comparison['evaluation_purpose'] == 'regression_seen_questions'
        assert comparison['fresh_holdout'] == 'unverified'
        assert len(ablation['results']) == 3600
        replay_keys, replay_totals = set(), Counter()
        for item in inventory:
            pid = item['project']
            fixture = ROOT / 'evaluation/github_readmes/projects' / pid
            questions = {q['id']: q for q in json.loads((fixture / 'evaluation/dataset.json').read_text('utf-8'))['questions']}
            body, _ = read_markdown(fixture / 'corpus/README.md')
            old_rows = json.loads((baseline / pid / 'retrieval.json').read_text('utf-8'))['results']
            old_by_key = {(r['id'], r['mode'], r['top_k']): r for r in old_rows}
            for row in [r for r in ablation['results'] if r['project'] == pid]:
                key = row['id'], row['mode'], row['top_k']
                assert key not in replay_keys
                replay_keys.add(key)
                assert row['selected_child_ids'] == old_by_key[key]['selected_child_ids']
                assert sum(len(c['formatted']) for c in row['context']) == row['context_chars'] <= 4000
                for block in row['context']:
                    assert body[block['start']:block['end']] == block['text']
                q = questions[row['id']]
                covered = all(evidence_covered(e, row['context']) for e in q['evidence']) if q['answerable'] else None
                assert row['complete_evidence_covered'] == covered
                if q['answerable']:
                    replay_totals[row['mode'], row['top_k']] += bool(covered)
        for row in ablation['summary']:
            if row['split'] == 'all' and row['kind'] == 'all':
                assert row['covered'] == replay_totals[row['mode'], row['top_k']]
        print('预算重放3600条：原候选不变、实际正文区间和覆盖统计核对通过；开发阶段与完整运行的代码哈希一致。')
    print(json.dumps({'projects': 20, 'questions': 600, 'retrieval_rows': count,
                      'actual_context_offsets_and_coverage': 'passed', 'top5_covered': totals,
                      'generation_records': 'correctly marked not_run' if not completion['model_configured'] else 'requires human review'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    verify(args.directory)

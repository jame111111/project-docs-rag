"""离线核对固定快照/题集，模型替身只验证流程，不评价语义效果。"""
import hashlib
import json

from app.config import ROOT
from app.documents import read_markdown
from app.chunking import section_spans
from evaluation.common import setup
from evaluation.github_readme_eval import summarize, verify_index
from conftest import OfflineEmbeddings

SUITE = ROOT / 'evaluation/github_readmes'


def test_twenty_readmes_and_six_hundred_fixed_questions():
    selected = json.loads((SUITE / 'selection.json').read_text('utf-8'))['projects']
    inventory = {d['project']: d for d in json.loads((SUITE / 'datasets.json').read_text('utf-8'))}
    assert len(selected) == len(inventory) == 20
    question_ids = set()
    for project in selected:
        directory = SUITE / 'projects' / project['id']
        source = json.loads((directory / 'source.json').read_text('utf-8'))
        path = directory / 'evaluation/dataset.json'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == inventory[project['id']]['dataset_sha256']
        assert hashlib.sha256((directory / 'corpus/README.md').read_bytes()).hexdigest() == source['sha256']
        assert len(source['commit']) == 40
        assert all((directory / 'licenses' / name).exists() for name in source['license_files'])
        body, _ = read_markdown(directory / 'corpus/README.md')
        spans = list(section_spans(body))
        questions = json.loads(path.read_text('utf-8'))['questions']
        assert len(questions) == 30
        assert sum(q['answerable'] for q in questions) == 24
        dev, final = set(), set()
        for q in questions:
            assert q['id'] not in question_ids
            question_ids.add(q['id'])
            assert bool(q['evidence']) == q['answerable']
            for e in q['evidence']:
                assert body[e['start']:e['end']] == e['quote']
                assert e['section'] == next(s[2] for s in spans if s[0] <= e['start'] < s[1])
            if q['answerable']:
                (dev if q['split'] == 'dev' else final).add(q['fact_group'])
        assert len(dev) == 9 and len(final) == 3
        assert not dev.intersection(final)
    assert len(question_ids) == 600


def test_suite_uses_isolated_runtime_and_injected_offline_vectors(tmp_path):
    settings, store, manager, retriever, questions, _ = setup('final',
        SUITE / 'projects/kubernetes/profile.json', tmp_path, embeddings=OfflineEmbeddings())
    index = verify_index(store, manager)
    assert settings.data_dir == tmp_path
    assert index['documents'] == 1
    assert len(questions) == 8
    assert retriever.retrieve(questions[0]['question'])['context']


def test_unsupported_rows_do_not_count_as_evidence_coverage():
    rows = [{'mode': 'hybrid_parent', 'top_k': 5, 'split': 'dev', 'kind': 'direct',
             'answerable': True, 'complete_evidence_covered': True, 'context_chars': 200, 'retrieval_ms': 10},
            {'mode': 'hybrid_parent', 'top_k': 5, 'split': 'dev', 'kind': 'unsupported',
             'answerable': False, 'complete_evidence_covered': None, 'context_chars': 100, 'retrieval_ms': 12}]
    result = next(r for r in summarize(rows) if r['split'] == 'all' and r['kind'] == 'all')
    assert result['questions'] == 2 and result['answerable'] == 1 and result['covered'] == 1
    assert result['complete_evidence_coverage'] == 1
    assert result['answer_accuracy'] == result['unsupported_answer_quality'] == 'unverified'

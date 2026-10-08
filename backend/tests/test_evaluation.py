import json

from app.chunking import chunk_document
from app.config import Settings
from app.products import load_manifest
from app.documents import read_markdown
from evaluation.common import FIXTURE_CONFIG, evidence_covered


def test_complete_evidence_uses_all_intervals():
    evidence = {'doc_id': 'one', 'start': 10, 'end': 30}
    assert evidence_covered(evidence, [{'doc_id': 'one', 'start': 0, 'end': 20}, {'doc_id': 'one', 'start': 20, 'end': 35}])
    assert not evidence_covered(evidence, [{'doc_id': 'one', 'start': 0, 'end': 19}, {'doc_id': 'one', 'start': 20, 'end': 35}])
    assert not evidence_covered(evidence, [{'doc_id': 'other', 'start': 0, 'end': 35}])


def test_frozen_dataset_and_actual_corpus_offsets():
    product = Settings(_env_file=None, product_config=FIXTURE_CONFIG).product
    manifest = load_manifest(product)
    dataset = json.loads(product.dataset_path.read_text('utf-8'))
    bodies = {d['id']: read_markdown(product.corpus_dir/d['snapshot_file'])[0] for d in manifest['documents']}
    assert len(dataset['questions']) == 40
    assert sum(q['answerable'] for q in dataset['questions']) == 30
    assert sum(q['split'] == 'final' for q in dataset['questions']) == 8
    for q in dataset['questions']:
        assert bool(q['evidence']) == q['answerable']
        for e in q['evidence']:
            assert bodies[e['doc_id']][e['start']:e['end']] == e['quote']
    for doc_id, body in bodies.items():
        parents, children = chunk_document(doc_id, body)
        assert ''.join(p.text for p in parents) == body
        parent_map = {p.id: p for p in parents}
        for child in children:
            parent = parent_map[child.parent_id]
            assert parent.start <= child.start < child.end <= parent.end
            assert body[child.start:child.end] == child.text
        for parent in parents:
            assert evidence_covered({'doc_id': doc_id, 'start': parent.start, 'end': parent.end},
                                    [c.__dict__ for c in children if c.parent_id == parent.id])

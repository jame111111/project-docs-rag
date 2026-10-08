import csv
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.config import ROOT, Settings
from app.storage import Store
from app.indexing import IndexManager
from app.retrieval import Retriever
from app.products import load_manifest
from app.cli import import_snapshot

MODES = ['vector_child', 'hybrid_child', 'hybrid_parent']
FIXTURE_CONFIG = ROOT / 'evaluation/fixtures/open-source/profile.json'
FIXTURE_RUNTIME = ROOT / 'data/runtime/evaluation-open-source'


def setup(split, config=None, data_dir=None, embeddings=None):
    # 评测使用独立本地夹具，应用启动及网页上传不读取这个目录。
    settings = Settings(product_config=config or FIXTURE_CONFIG, data_dir=data_dir or FIXTURE_RUNTIME)
    store = Store(settings.data_dir / 'metadata.sqlite3')
    store.bind_product(settings.product.id)
    dataset_path = settings.product.dataset_path
    if not dataset_path or not dataset_path.exists():
        raise ValueError('当前测试配置没有评测集，请指定带有已核对题集的配置。')
    dataset = json.loads(dataset_path.read_text('utf-8'))
    if not store.documents():
        import_snapshot(store, settings)
    for q in dataset['questions']:
        for e in q['evidence']:
            doc = store.document(e['doc_id'])
            if not doc or doc['body'][e['start']:e['end']] != e['quote']:
                raise ValueError(f"{q['id']} 的固定证据与资料不一致，请恢复快照，禁止自动放宽评测")
    manager = IndexManager(store, settings, embeddings=embeddings)
    if store.state()['status'] != 'ready':
        manager.rebuild()
    manager.ensure_ready()
    manifest = load_manifest(settings.product)
    if {d['id'] for d in store.documents()} != {d['id'] for d in manifest['documents']}:
        raise ValueError('资料库含额外或缺失文档。请使用新的 DATA_DIR 导入固定快照评测。')
    questions = [q for q in dataset['questions'] if split == 'all' or q['split'] == split]
    metadata = {'product_id': settings.product.id, 'product_name': settings.product.name,
        'corpus_commit': dataset['corpus_commit'], 'dataset_sha256': hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        'embedding_model': settings.embedding_model, 'embedding_revision': settings.embedding_revision,
        'index_fingerprint': store.state()['fingerprint'],
        'context_budget': settings.context_budget, 'candidates_per_route': 10, 'rrf_k': 60,
        'split': split, 'question_count': len(questions), 'answerable_count': sum(q['answerable'] for q in questions)}
    return settings, store, manager, Retriever(manager), questions, metadata


def output_dir(kind):
    import uuid
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    path = ROOT / 'evaluation/results' / f'run-{kind}-{now}-{uuid.uuid4().hex[:6]}'
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def evidence_covered(evidence, context):
    """区间并集完全覆盖每一处所需原文；不把标题、命中词当证据。"""
    cursor = evidence['start']
    for block in sorted(context, key=lambda c: c['start']):
        if block['doc_id'] != evidence['doc_id'] or block['end'] <= cursor:
            continue
        if block['start'] > cursor:
            break
        cursor = max(cursor, block['end'])
        if cursor >= evidence['end']:
            return True
    return False

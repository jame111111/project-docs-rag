"""核对当前产品的快照、证据与已保存结果，不调用生成模型或重跑最终题。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.config import Settings
from app.products import load_manifest
from app.indexing import IndexManager
from app.storage import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path)
    parser.add_argument('--config', type=Path, default=ROOT/'evaluation/fixtures/open-source/profile.json')
    parser.add_argument('--data-dir', type=Path, default=ROOT/'data/runtime/evaluation-open-source')
    args = parser.parse_args()
    settings = Settings(product_config=args.config, data_dir=args.data_dir)
    manifest = load_manifest(settings.product)
    for doc in manifest['documents']:
        assert hashlib.sha256((settings.product.corpus_dir/doc['snapshot_file']).read_bytes()).hexdigest() == doc['sha256']
    store = Store(settings.data_dir/'metadata.sqlite3')
    manager = IndexManager(store, settings)
    state = manager.ensure_ready()
    assert {d['id'] for d in store.documents()} == {d['id'] for d in manifest['documents']}
    assert len(manager.chroma().list_collections()) == 1
    if settings.product.dataset_path:
        dataset_path = settings.product.dataset_path
        dataset = json.loads(dataset_path.read_text('utf-8'))
        for q in dataset['questions']:
            for e in q['evidence']:
                assert store.document(e['doc_id'])['body'][e['start']:e['end']] == e['quote']
        if args.results:
            for split in ['dev', 'final', 'answers']:
                run = json.loads((args.results/split/'results.json').read_text('utf-8'))
                assert run['metadata']['product_id'] == settings.product.id
                assert run['metadata']['index_fingerprint'] == state['fingerprint']
                assert run['metadata']['dataset_sha256'] == hashlib.sha256(dataset_path.read_bytes()).hexdigest()
                assert len(run['results']) == run['metadata']['question_count'] * 6
                if split != 'answers':
                    for row in run['results']:
                        assert row['context_chars'] == sum(len(c['formatted']) for c in row['context']) <= settings.context_budget
    print(f"一致性核对通过：{settings.product.name} / {state['documents']} 文档 / {state['parents']} 父块 / {state['children']} 子块")


if __name__ == '__main__':
    main()

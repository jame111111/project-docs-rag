"""离线测试：通用产品替换、独立目录、快照更新与来源，不评估生成质量。"""
import json

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.cli import import_snapshot, prepare_manifest
from app.config import Settings
from app.products import load_product
from app.storage import Store
from app.indexing import IndexManager, IndexUnavailable
from conftest import OfflineEmbeddings


def make_product(tmp_path, pid, name):
    root = tmp_path/pid
    (root/'corpus').mkdir(parents=True)
    profile = root/'product.json'
    profile.write_text(json.dumps({'id': pid, 'name': name, 'description': '本地帮助',
        'source_label': '自行编写', 'examples': [{'question': '怎么打开设置？',
        'doc_id': pid + '-settings', 'quote': '点击设置。'}]}, ensure_ascii=False), 'utf-8')
    (root/'corpus/settings.md').write_text(f'---\ndoc_id: {pid}-settings\nsource_url: https://example.com/help\n---\n# 设置\n\n点击设置。\n', 'utf-8')
    settings = Settings(_env_file=None, product_config=profile, data_dir=tmp_path/('runtime-' + pid))
    prepare_manifest(settings)
    return settings


def test_any_product_works_without_dataset(tmp_path):
    settings = make_product(tmp_path, 'qq', 'QQ')
    store = Store(settings.data_dir/'metadata.sqlite3')
    import_snapshot(store, settings)
    app = create_app(settings, embeddings=OfflineEmbeddings())
    client = TestClient(app)
    health = client.get('/api/health').json()
    assert health['product']['name'] == 'QQ'
    assert 'corpus' not in health['product'] and 'data_dir' not in health
    assert client.get('/api/examples').json()['questions'] == ['怎么打开设置？']
    assert client.get('/api/documents').json()['documents'][0]['source_label'] == '自行编写'
    app.state.manager.rebuild()
    assert len(app.state.manager.children) > 0


def test_product_runtime_isolation_and_wrong_directory_guard(tmp_path):
    first = make_product(tmp_path, 'qq', 'QQ')
    second = make_product(tmp_path, 'bilibili', '哔哩哔哩')
    for settings in [first, second]:
        store = Store(settings.data_dir/'metadata.sqlite3')
        import_snapshot(store, settings)
    assert first.data_dir != second.data_dir
    wrong = Settings(_env_file=None, product_config=second.product_config, data_dir=first.data_dir)
    with pytest.raises(ValueError, match='其他产品'):
        create_app(wrong)
    automatic = Settings(_env_file=None, product_config=second.product_config)
    assert automatic.data_dir.name == 'bilibili'


def test_snapshot_updates_and_removals_preserve_uploads(tmp_path):
    settings = make_product(tmp_path, 'qq', 'QQ')
    store = Store(settings.data_dir/'metadata.sqlite3')
    import_snapshot(store, settings)
    manager = IndexManager(store, settings, OfflineEmbeddings())
    manager.rebuild()
    original = store.document('qq-settings')
    store.save_document({**original, 'id': 'upload-one', 'metadata': {'source_label': '用户上传'}})
    path = settings.product.corpus_dir/'settings.md'
    path.write_text('---\ndoc_id: qq-new\n---\n# 新版\n\n点击新版设置。\n', 'utf-8')
    prepare_manifest(settings)
    import_snapshot(store, settings)
    assert store.document('qq-settings') is None
    assert store.document('upload-one')
    assert store.state()['status'] == 'stale'
    with pytest.raises(IndexUnavailable):
        manager.ensure_ready()
    manager.rebuild()
    assert {c['doc_id'] for c in store.chunks('child')} == {'qq-new', 'upload-one'}
    assert len(manager.chroma().list_collections()) == 1
    path.write_text('---\ndoc_id: qq-new\n---\n# 新版\n\n先登录。再点击新版设置。\n', 'utf-8')
    prepare_manifest(settings)
    import_snapshot(store, settings)  # 同 ID 更新，不能因 INSERT OR REPLACE 触发外键错误。
    manager.rebuild()
    doc = store.document('qq-new')
    for child in store.chunks('child'):
        if child['doc_id'] == 'qq-new':
            assert doc['body'][child['start']:child['end']] == child['text']


def test_bad_pack_does_not_partially_update(tmp_path):
    settings = make_product(tmp_path, 'qq', 'QQ')
    store = Store(settings.data_dir/'metadata.sqlite3')
    import_snapshot(store, settings)
    before = store.documents()
    (settings.product.corpus_dir/'settings.md').write_text('# 被篡改\n', 'utf-8')
    with pytest.raises(ValueError, match='校验失败'):
        import_snapshot(store, settings)
    assert store.documents() == before


def test_product_config_cannot_escape_pack(tmp_path):
    settings = make_product(tmp_path, 'qq', 'QQ')
    raw = json.loads(settings.product_config.read_text('utf-8'))
    raw['corpus'] = '../../outside'
    settings.product_config.write_text(json.dumps(raw), 'utf-8')
    with pytest.raises(ValueError, match='产品目录'):
        load_product(settings.product_config)

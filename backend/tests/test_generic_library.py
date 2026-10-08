"""离线流程测试：任意 Markdown 均可入库，无须项目配置或测试语料。"""
from app.config import Settings


def test_default_profile_has_no_fixture_dependency(client):
    settings = Settings(_env_file=None)
    assert settings.product.id == 'knowledge-base'
    assert settings.product.dataset_path is None
    assert settings.product.examples == []
    assert 'evaluation' not in str(settings.product_config)
    health = client.get('/api/health').json()
    assert health['document_count'] == 0
    assert health['product']['source_url'] == ''
    assert client.get('/api/examples').json() == {'questions': []}
    assert client.get('/api/documents').json() == {'documents': []}
    assert client.post('/api/ask', json={'question': '怎么启动？'}).json()['detail']['code'] == 'corpus_empty'


def test_arbitrary_readmes_share_generic_pipeline(client, offline_app):
    bodies = ['# Alpha\n\n## 启动\n\n先安装依赖，再启动服务。\n',
              '# Beta\n\n## 贡献\n\n提交前运行检查。\n\n```bash\ncheck --all\n```\n']
    doc_ids = []
    for filename, text in zip(['README.md', 'CONTRIBUTING.md'], bodies):
        response = client.post('/api/documents', files={'file': (filename, text.encode(), 'text/markdown')})
        assert response.status_code == 201
        doc_ids.append(response.json()['id'])
    manager = offline_app.state.manager
    manager.rebuild()
    assert {doc['id'] for doc in manager.store.documents()} == set(doc_ids)
    assert {child['doc_id'] for child in manager.children} == set(doc_ids)
    for child in manager.children:
        body = client.get('/api/documents/' + child['doc_id']).json()['body']
        assert body[child['start']:child['end']] == child['text']
    assert manager.collection.count() == len(manager.children)


def test_document_update_preserves_id_and_disables_old_index(client, offline_app):
    original = client.post('/api/documents', files={'file': ('README.md', '# 项目\n\n旧版启动命令。'.encode())}).json()
    manager = offline_app.state.manager
    manager.rebuild()
    replacement = '# 项目\n\n## 启动\n\n新版先检查环境。\n'
    response = client.put('/api/documents/' + original['id'], files={'file': ('../../README.md', replacement.encode())})
    assert response.status_code == 200
    assert response.json()['id'] == original['id']
    assert len(manager.store.documents()) == 1
    assert manager.store.state()['status'] == 'stale'
    assert client.post('/api/ask', json={'question': '如何启动？'}).json()['detail']['code'] == 'index_unavailable'
    manager.rebuild()
    assert all('旧版' not in child['text'] for child in manager.children)
    assert {child['doc_id'] for child in manager.children} == {original['id']}
    assert len(manager.chroma().list_collections()) == 1
    assert client.put('/api/documents/missing', files={'file': ('README.md', replacement.encode())}).status_code == 404
    count = len(manager.store.documents())
    client.post('/api/documents', files={'file': ('README.md', replacement.encode())})
    assert len(manager.store.documents()) == count + 1  # 不覆盖另一项目的同名文件。

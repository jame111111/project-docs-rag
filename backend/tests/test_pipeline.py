import json
import threading

import pytest

from app.answering import LLMClient, LLMError, ModelAnswer, validate_citations
from app.chunking import chunk_document
from app.config import Settings
from app.documents import normalize_markdown
from app.indexing import IndexUnavailable
from app.retrieval import build_context, rrf


def test_normalization_and_metadata():
    body, meta = normalize_markdown('---\ntitle: 测试\npermalink: test\n---\r\n# 标题\r\n[[目标|显示文字]]\n`[[代码|保留]]`\n', 'fallback')
    assert meta['title'] == '测试' and meta['permalink'] == 'test'
    assert '显示文字' in body and '`[[代码|保留]]`' in body and '\r' not in body
    _, meta = normalize_markdown('```md\n# 代码里的标题\n```\n正文', '真实文件名')
    assert meta['title'] == '真实文件名'
    _, meta = normalize_markdown('---\ncollected_at: 2026-10-05\n---\n正文', '日期')
    assert meta['collected_at'] == '2026-10-05'


@pytest.mark.parametrize('raw', ['---\na: [\n---\n正文', '---\ntitle: a', '   ', '---\n- a\n---\n正文'])
def test_invalid_markdown(raw):
    with pytest.raises(ValueError):
        normalize_markdown(raw, 'title')


def test_offsets_repeat_steps_and_fences():
    repeat = '重复文本，必须引用当前位置。\n\n'
    body = '# 一\n\n' + repeat * 80 + '## 二\n\n' + repeat + '1. 先打开设置。\n2. 注意前置条件。\n\n```md\n# 假标题\n\n代码\n```\n'
    parents, children = chunk_document('doc', body)
    assert ''.join(p.text for p in parents) == body
    by_id = {p.id: p for p in parents}
    assert len({c.id for c in children}) == len(children)
    for child in children:
        parent = by_id[child.parent_id]
        assert parent.start <= child.start < child.end <= parent.end
        assert body[child.start:child.end] == child.text
        assert '假标题' not in child.section
    assert any('1. 先打开设置。\n2. 注意前置条件。' in p.text for p in parents)
    second = [p for p in parents if p.section.endswith('二')][0]
    context = [{**second.__dict__, 'ref': 1, 'title': '文档', 'source_url': ''}]
    output = ModelAnswer(status='answered', answer='有依据 [1]', citations=[{'ref': 1, 'quote': repeat.strip()}])
    citation = validate_citations(output, context)['citations'][0]
    assert citation['start'] >= body.index('## 二')
    assert body[citation['start']:citation['end']] == citation['quote']


def test_long_sentence_progress_and_no_loss():
    body = '短句。' + '很' * 1500 + '长句。最后一句。'
    parents, children = chunk_document('doc', body)
    assert len(children) < 10
    intervals = sorted((c.start, c.end) for c in children)
    end = 0
    for start, next_end in intervals:
        assert start <= end
        end = max(end, next_end)
    assert end == len(body)


def test_rrf_deduplicates():
    ids, scores = rrf(['b', 'a', 'a'], ['a', 'c'])
    assert ids[0] == 'a' and len(ids) == 3
    assert scores['a'] == pytest.approx(1/62 + 1/61)


def test_quote_rejection():
    context = [{'ref': 1, 'doc_id': 'doc', 'title': '测试', 'section': '章节',
                'text': '真实证据。', 'start': 20, 'source_url': ''}]
    for citations in [[{'ref': 9, 'quote': '真实证据。'}], [{'ref': 1, 'quote': '虚构文本'}], []]:
        result = validate_citations(ModelAnswer(status='answered', answer='一段断言', citations=citations), context)
        assert result['status'] == 'insufficient_evidence' and result['citations'] == []
    result = validate_citations(ModelAnswer(status='answered', answer='答案 [1] [9]',
        citations=[{'ref': 1, 'quote': '真实证据。'}]), context)
    assert '[9]' not in result['answer']


def upload(client, name='例子.md', text='# 例子\n\n步骤一。\n\n步骤二。'):
    return client.post('/api/documents', files={'file': (name, text.encode('utf-8'), 'text/markdown')})


def test_upload_guard_and_internal_paths(client):
    assert upload(client, 'wrong.txt').status_code == 415
    assert client.post('/api/documents', files={'file': ('x.md', b'\xff')}).status_code == 422
    assert upload(client, 'x.md', 'x' * (1048576 + 1)).status_code == 413
    assert upload(client, 'x.md', '---\na: [\n---\n正文').status_code == 422
    response = upload(client, '../../escape.md')
    assert response.status_code == 201
    doc = response.json()
    assert doc['title'] == '例子' and 'source_path' not in doc
    reader = client.get('/api/documents/' + doc['id']).json()
    assert 'source_path' not in reader and reader['body'].startswith('# 例子')
    assert client.get('/api/documents/missing').status_code == 404
    declared = upload(client, 'source.md', '---\nsource_label: 官方认证\n---\n# 自行上传\n正文')
    assert declared.json()['source_label'] == '用户上传'


def test_upload_rebuild_consistency(client, offline_app):
    doc = upload(client).json()
    manager = offline_app.state.manager
    manager.rebuild()
    assert manager.collection.count() == len(manager.store.chunks('child'))
    assert client.post('/api/ask', json={'question': '如何操作？'}).json()['detail']['code'] == 'model_not_configured'
    assert client.post('/api/ask', json={'question': '   '}).status_code == 422
    old_count = manager.collection.count()
    manager.rebuild()
    assert manager.collection.count() == old_count
    assert len(manager.chroma().list_collections()) == 1
    upload(client, '新.md', '# 新资料\n\n另一个步骤。')
    assert manager.store.state()['status'] == 'stale'
    assert client.post('/api/ask', json={'question': '问题'}).json()['detail']['code'] == 'index_unavailable'
    manager.rebuild()
    assert manager.collection.count() > old_count
    contexts, chars = build_context(manager.store, [c['id'] for c in manager.children], budget=4000)
    assert len(contexts) <= 3 and chars <= 4000
    assert len({c['id'] for c in contexts}) == len(contexts)
    assert build_context(manager.store, [manager.children[0]['id']], budget=1)[0] == []


def test_failure_disables_old_index(client, offline_app):
    upload(client)
    manager = offline_app.state.manager
    manager.rebuild()
    def fail(*args, **kwargs):
        raise RuntimeError('offline injected failure')
    manager.embeddings.encode = fail
    with pytest.raises(RuntimeError):
        manager.rebuild()
    assert manager.store.state()['status'] == 'failed'
    with pytest.raises(IndexUnavailable):
        manager.ensure_ready()


def test_busy_states(client, offline_app):
    upload(client)
    manager = offline_app.state.manager
    manager.begin()
    assert upload(client).status_code == 409
    assert client.post('/api/index/rebuild').status_code == 409


def test_model_schema_and_network_errors(monkeypatch):
    import httpx
    settings = Settings(_env_file=None, llm_base_url='https://example.invalid/v1', llm_api_key='test-placeholder', llm_model='offline')
    def invalid(*args, **kwargs):
        return httpx.Response(200, request=httpx.Request('POST', settings.llm_base_url),
                              json={'choices': [{'message': {'content': '{"status":"answered"}'}}]})
    monkeypatch.setattr(httpx.Client, 'post', invalid)
    with pytest.raises(LLMError, match='invalid_model_output'):
        LLMClient(settings).answer('问题', [])
    def network(*args, **kwargs):
        raise httpx.ConnectError('offline injected error')
    monkeypatch.setattr(httpx.Client, 'post', network)
    with pytest.raises(LLMError, match='model_request_failed'):
        LLMClient(settings).answer('问题', [])

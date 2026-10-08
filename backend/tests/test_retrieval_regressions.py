"""离线回归：由真实 README 测试暴露的预算故障和关键词噪声。"""
import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.indexing import IndexUnavailable, tokenize
from app.retrieval import build_context


class ContextStore:
    def __init__(self):
        shell = '启动命令：spark-shell。'
        self.body = '长' * 5000 + shell + '其他章节。'
        shell_end = 5000 + len(shell)
        self.parents = [self.block('large', 0, 5000), self.block('shell', 5000, shell_end),
                        self.block('other', shell_end, len(self.body))]
        self.children = [dict(self.block('hit-large', 100, 200), parent_id='large'),
                         dict(self.parents[1], id='hit-shell', parent_id='shell'),
                         dict(self.parents[2], id='hit-other', parent_id='other')]

    def block(self, name, start, end):
        return {'id': name, 'doc_id': 'readme', 'parent_id': None, 'section': name,
                'start': start, 'end': end, 'text': self.body[start:end]}

    def chunks(self, kind):
        return self.parents if kind == 'parent' else self.children

    def documents(self):
        return [{'id': 'readme', 'title': 'README', 'source_url': ''}]


def test_oversized_first_parent_does_not_hide_later_command():
    store, diagnostics = ContextStore(), []
    context, used = build_context(store, ['hit-large', 'hit-shell', 'hit-shell', 'hit-other'],
                                  diagnostics=diagnostics)
    assert [b['id'] for b in context] == ['shell', 'other']
    assert [b['ref'] for b in context] == [1, 2]
    assert 'spark-shell' in context[0]['text']
    assert used == sum(len(b['formatted']) for b in context) <= 4000
    assert diagnostics[0]['reason'] == 'context_budget'
    for b in context:
        assert b['text'] == store.body[b['start']:b['end']]


def test_packing_skips_blocks_without_truncation_or_extra_candidates():
    store = ContextStore()
    # top_k=1 的大块仍放不下，不偷偷扩大候选或使用子块假冒父块。
    assert build_context(store, ['hit-large'])[0] == []
    first, size = build_context(store, ['hit-shell'])
    context, used = build_context(store, ['hit-shell', 'hit-large', 'hit-other'], budget=size)
    assert context == first and used == size


def test_keyword_noise_and_technical_terms():
    terms = tokenize('请问，如何使用 C++ CUDA docker-compose environment_name --log-level？')
    assert {'c++', 'cuda', 'docker-compose', 'environment_name', '--log-level'} <= set(terms)
    assert not {'请问', '如何', '，', '？', '-', '_'} & set(terms)
    assert tokenize('？！！请问怎么呢') == []
    assert tokenize('the CUDA and Python requirements') == ['cuda', 'python', 'requirements']


def test_algorithm_change_invalidates_old_index_at_startup(client, offline_app):
    client.post('/api/documents', files={'file': ('README.md', b'# Start\n\nRun python app.py.\n')})
    manager = offline_app.state.manager
    manager.rebuild()
    state = manager.store.state()
    old_generation = state['generation']
    manager.store.set_state({**state, 'fingerprint': 'old-algorithm'})
    restarted = create_app(manager.settings, embeddings=manager.embeddings)
    restarted_client = TestClient(restarted)
    health = restarted_client.get('/api/health').json()
    assert health['index']['status'] == 'stale'
    assert '算法' in health['index']['message']
    assert restarted_client.post('/api/ask', json={'question': '如何启动？'}).json()['detail']['code'] == 'index_unavailable'
    with pytest.raises(IndexUnavailable):
        restarted.state.manager.ensure_ready()
    restarted.state.manager.rebuild()
    assert restarted.state.manager.ensure_ready()['status'] == 'ready'
    assert restarted.state.manager.collection.name != old_generation
    assert len(restarted.state.manager.chroma().list_collections()) == 1
    assert len(restarted.state.store.chunks('child')) == restarted.state.manager.collection.count()


def test_empty_keyword_document_still_builds_and_queries(client, offline_app):
    client.post('/api/documents', files={'file': ('!!!.md', b'# !!!\n\n????')})
    manager = offline_app.state.manager
    manager.rebuild()
    assert all(score == 0 for score in manager.bm25.get_scores(tokenize('请问怎么呢？')))

"""一次重建一个新集合，成功后原子发布；失败则明确禁用索引。"""
import hashlib
import json
import logging
import re
import threading
import uuid
from pathlib import Path
from dataclasses import asdict

from .chunking import chunk_document

log = logging.getLogger(__name__)

# 变化会使旧索引失效，包括持久化的 BM25 分词结果。
INDEX_VERSION = 'chunking-v2-keywords-v2'
STOPWORDS = frozenset('''的 了 在 是 和 与 或 吗 呢 我 我们 你 你们 这 这个 那 那个
一个 该 请 请问 如何 怎么 怎样 什么 哪些 为什么 是否 可以 能 想 要 有
a an the and or of to in on for with is are was were be been this that
it its i we you how what which can could would please do does'''.split())


class IndexUnavailable(Exception):
    pass


class Embeddings:
    def __init__(self, settings):
        self.settings, self.model = settings, None

    def encode(self, texts, query=False):
        if self.model is None:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.settings.embedding_model,
                                            device=self.settings.embedding_device,
                                            revision=None if Path(self.settings.embedding_model).is_dir() else self.settings.embedding_revision,
                                            local_files_only=self.settings.embedding_local_only)
        if query:
            texts = ['为这个句子生成表示以用于检索相关文章：' + t for t in texts]
        return self.model.encode(texts, normalize_embeddings=True, batch_size=32,
                                 show_progress_bar=False).tolist()


def tokenize(text):
    import jieba
    # 中文用 jieba；技术标识符保留连接符/下划线，避免被拆成通用碎词。
    pieces = re.findall(r'(?:--)?[A-Za-z_][A-Za-z0-9_]*(?:[-./][A-Za-z0-9_]+)*(?:\+\+|#)?|'
                        r'[0-9]+(?:\.[0-9]+)*|[\u3400-\u9fff]+', text)
    tokens = []
    for piece in pieces:
        words = jieba.lcut(piece) if '\u3400' <= piece[0] <= '\u9fff' else [piece]
        tokens.extend(w.lower() for w in words if w.lower() not in STOPWORDS)
    return tokens


class IndexManager:
    def __init__(self, store, settings, embeddings=None):
        self.store, self.settings = store, settings
        self.embeddings = embeddings or Embeddings(settings)
        self.lock = threading.RLock()
        self.client = None
        self.loaded_generation = None
        self.collection, self.bm25, self.children = None, None, []
        if store.state()['status'] == 'building':
            store.set_state({'status': 'failed', 'message': '上次重建被中断，请重新建立索引'})
        elif store.state()['status'] == 'ready':
            self.invalidate_changed_index()

    def chroma(self):
        if self.client is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            self.client = chromadb.PersistentClient(str(self.settings.data_dir / 'chroma'),
                settings=ChromaSettings(anonymized_telemetry=False))
        return self.client

    def fingerprint(self):
        docs = self.store.documents()
        content = [(d['id'], d['title'], d['body'], d['version'], d['source_url']) for d in docs]
        return hashlib.sha256(json.dumps([INDEX_VERSION, self.settings.product.id, self.settings.embedding_model,
            self.settings.embedding_revision, content],
            ensure_ascii=False).encode()).hexdigest()

    def invalidate_changed_index(self):
        state = self.store.state()
        if state['status'] == 'ready' and state.get('fingerprint') != self.fingerprint():
            self.loaded_generation = None
            self.store.set_state({'status': 'stale', 'message': '文档、索引算法或向量模型配置已变化，请重建索引'})
        return self.store.state()

    def begin(self):
        with self.lock:
            if self.store.state()['status'] == 'building':
                raise IndexUnavailable('索引正在重建')
            self.store.set_state({'status': 'building', 'message': '正在分块、向量化和建立关键词索引'})

    def rebuild(self, begun=False):
        if not begun:
            self.begin()
        with self.lock:
            generation = 'children_' + uuid.uuid4().hex
            try:
                docs = self.store.documents()
                if not docs:
                    raise ValueError('资料库为空，请先导入 Markdown')
                parents, children, texts = [], [], []
                for doc in docs:
                    p, c = chunk_document(doc['id'], doc['body'])
                    parents.extend(p)
                    children.extend(c)
                    texts.extend(f"{doc['title']}\n{x.section}\n{x.text}" for x in c)
                vectors = self.embeddings.encode(texts)
                collection = self.chroma().create_collection(generation,
                    metadata={'hnsw:space': 'cosine'}, embedding_function=None)
                for start in range(0, len(children), 128):
                    batch = children[start:start + 128]
                    collection.add(ids=[c.id for c in batch], embeddings=vectors[start:start + 128])
                tokens = [tokenize(text) for text in texts]
                token_path = self.settings.data_dir / f'{generation}.json'
                token_path.write_text(json.dumps(tokens, ensure_ascii=False), encoding='utf-8')
                state = {'status': 'ready', 'message': '索引可用', 'generation': generation,
                         'fingerprint': self.fingerprint(), 'documents': len(docs),
                         'parents': len(parents), 'children': len(children)}
                self.store.replace_index(parents, children, state)
                self.loaded_generation = None
                self.ensure_ready()
                # 只保留本项目当前子块集合；不会操作外部 Chroma。
                for old in self.chroma().list_collections():
                    if old.name.startswith('children_') and old.name != generation:
                        self.chroma().delete_collection(old.name)
                for old in self.settings.data_dir.glob('children_*.json'):
                    if old != token_path:
                        old.unlink()
                return state
            except Exception as exc:
                log.exception('Index rebuild failed')
                self.loaded_generation = None
                self.store.set_state({'status': 'failed', 'message':
                    '索引重建失败：请检查本地模型文件、依赖和日志，然后重试',
                    'error_type': type(exc).__name__})
                if self.client is not None:
                    try:
                        self.client.delete_collection(generation)
                    except Exception:
                        pass
                raise

    def ensure_ready(self):
        state = self.store.state()
        if state['status'] != 'ready':
            raise IndexUnavailable(state['message'])
        state = self.invalidate_changed_index()
        if state['status'] != 'ready':
            raise IndexUnavailable(state['message'])
        if self.loaded_generation != state['generation']:
            try:
                from rank_bm25 import BM25Okapi
                tokens = json.loads((self.settings.data_dir / f"{state['generation']}.json").read_text('utf-8'))
                self.children = self.store.chunks('child')
                self.collection = self.chroma().get_collection(state['generation'], embedding_function=None)
                if len(tokens) != len(self.children) or self.collection.count() != len(self.children):
                    raise ValueError('SQLite 与索引数量不一致')
                # 全是标点的文档也可以阅读/入库；占位词不会成为用户问题的关键词。
                self.bm25 = BM25Okapi([row or ['__empty_document__'] for row in tokens])
                self.loaded_generation = state['generation']
            except Exception as exc:
                self.store.set_state({'status': 'failed', 'message': '索引文件缺失或损坏，请重建索引'})
                raise IndexUnavailable('索引文件缺失或损坏，请重建索引') from exc
        return state

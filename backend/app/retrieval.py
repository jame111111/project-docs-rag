"""子块双路检索与 RRF；上下文只放完整块，不截断。"""
from time import perf_counter

from .indexing import IndexUnavailable, tokenize


def rrf(vector_ids, keyword_ids, k=60):
    scores = {}
    for ids in [vector_ids, keyword_ids]:
        for rank, child_id in enumerate(dict.fromkeys(ids), start=1):
            scores[child_id] = scores.get(child_id, 0) + 1 / (k + rank)
    return sorted(scores, key=lambda cid: (-scores[cid], cid)), scores


def build_context(store, child_ids, mode='hybrid_parent', budget=4000, diagnostics=None):
    children = {c['id']: c for c in store.chunks('child')}
    parents = {p['id']: p for p in store.chunks('parent')}
    docs = {d['id']: d for d in store.documents()}
    selected, seen, used = [], set(), 0
    for child_id in child_ids:
        child = children[child_id]
        block = parents[child['parent_id']] if mode == 'hybrid_parent' else child
        if block['id'] in seen:
            continue
        seen.add(block['id'])
        doc = docs[block['doc_id']]
        ref = len(selected) + 1
        header = f"[{ref}] 文档：{doc['title']}\n章节：{block['section']}\n"
        formatted = header + block['text'] + '\n'
        if used + len(formatted) > budget:
            # 跳过放不下的完整块，继续检查后面的命中；不截断，也不扩充 top_k。
            if diagnostics is not None:
                diagnostics.append({'block_id': block['id'], 'reason': 'context_budget',
                                    'block_chars': len(formatted), 'remaining_chars': budget - used})
            continue
        selected.append({**block, 'ref': ref, 'title': doc['title'],
                         'source_url': doc['source_url'], 'formatted': formatted})
        used += len(formatted)
        if mode == 'hybrid_parent' and len(selected) == 3:
            break
    return selected, used


class Retriever:
    def __init__(self, manager):
        self.manager = manager

    def candidates(self, question, candidate_count=10):
        manager = self.manager
        if manager.store.state()['status'] == 'building':
            raise IndexUnavailable('索引正在重建，请稍后重试')
        with manager.lock:
            manager.ensure_ready()
            started = perf_counter()
            vector = manager.embeddings.encode([question], query=True)
            result = manager.collection.query(query_embeddings=vector,
                n_results=min(candidate_count, len(manager.children)), include=['distances'])
            vector_ids = result['ids'][0]
            vector_ms = (perf_counter() - started) * 1000
            started = perf_counter()
            scores = manager.bm25.get_scores(tokenize(question))
            ranked = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), manager.children[i]['id']))
            keyword_ids = [manager.children[i]['id'] for i in ranked if scores[i] > 0][:candidate_count]
            keyword_ms = (perf_counter() - started) * 1000
            fused, fusion_scores = rrf(vector_ids, keyword_ids)
            return {'vector_ids': vector_ids, 'keyword_ids': keyword_ids, 'fused_ids': fused,
                    'rrf_scores': fusion_scores, 'vector_ms': vector_ms, 'keyword_ms': keyword_ms,
                    'distances': result['distances'][0]}

    def retrieve(self, question, mode='hybrid_parent', top_k=5):
        started = perf_counter()
        with self.manager.lock:
            candidates = self.candidates(question)
            ids = (candidates['vector_ids'] if mode == 'vector_child' else candidates['fused_ids'])[:top_k]
            context_diagnostics = []
            context, chars = build_context(self.manager.store, ids, mode,
                self.manager.settings.context_budget, context_diagnostics)
        return {'context': context, 'context_chars': chars,
                'retrieval_ms': round((perf_counter() - started) * 1000, 2),
                'diagnostics': {**candidates, 'context_skipped': context_diagnostics}}

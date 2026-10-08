"""文档问答 REST。公开 DTO 不返回服务器路径，字段与前端 api.ts 一致。"""
import json
import logging
import threading
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from .answering import LLMClient, LLMError, answer_question
from .config import ROOT, Settings
from .documents import normalize_markdown
from .indexing import IndexManager, IndexUnavailable
from .retrieval import Retriever
from .storage import Store


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

    @field_validator('question')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('问题不能为空')
        return value.strip()


def public_document(doc, status):
    metadata = doc['metadata'] if isinstance(doc['metadata'], dict) else json.loads(doc['metadata'])
    return {k: doc[k] for k in ['id', 'title', 'category', 'source_url', 'collected_at', 'version']} | {
        'index_status': 'indexed' if status == 'ready' else 'pending',
        'source_label': metadata.get('source_label', '用户上传')}


def create_app(settings=None, embeddings=None, llm=None):
    settings = settings or Settings()
    store = Store(settings.data_dir / 'metadata.sqlite3')
    store.bind_product(settings.product.id)
    manager = IndexManager(store, settings, embeddings)
    retriever = Retriever(manager)
    llm = llm or LLMClient(settings)
    app = FastAPI(title='开源项目入门助手', version='1.0.0')
    app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
                       allow_methods=['GET', 'POST', 'PUT'], allow_headers=['Content-Type'])
    app.state.store, app.state.manager = store, manager

    @app.get('/api/health')
    def health():
        state = store.state()
        return {'status': 'ok', 'product': settings.product.public_info(), 'index': state,
                'model_configured': settings.llm_configured, 'document_count': len(store.documents())}

    @app.get('/api/examples')
    def examples():
        # 示例来自产品配置，不依赖评测集；无评测集的新产品也能使用。
        questions = [item.question for item in settings.product.examples
                     if (doc := store.document(item.doc_id)) and item.quote in doc['body']]
        return {'questions': questions[:4]}

    @app.get('/api/documents')
    def documents(q: str = ''):
        status = store.state()['status']
        return {'documents': [public_document(d, status) for d in store.documents()
                             if q.lower() in (d['title'] + d['category']).lower()]}

    @app.get('/api/documents/{doc_id}')
    def document(doc_id: str):
        doc = store.document(doc_id)
        if not doc:
            raise HTTPException(404, detail={'code': 'document_not_found', 'message': '文档不存在'})
        return {**public_document(doc, store.state()['status']), 'body': doc['body'],
                'offset_unit': 'unicode_codepoint'}

    async def save_upload(file: UploadFile, doc_id=None):
        if not file.filename or not file.filename.lower().endswith('.md'):
            raise HTTPException(415, detail={'code': 'invalid_file_type', 'message': '只接受 UTF-8 的 .md 文件'})
        raw = await file.read(settings.upload_max_bytes + 1)
        await file.close()
        if len(raw) > settings.upload_max_bytes:
            raise HTTPException(413, detail={'code': 'upload_too_large', 'message': '文件超过上传大小上限（默认 1 MB）'})
        # filename 仅作为展示标题，保存路径由后端 UUID 决定。
        title = file.filename.replace('\\', '/').split('/')[-1][:-3][:120]
        try:
            decoded = raw.decode('utf-8-sig')
            if '\x00' in decoded:
                raise ValueError('不接受含空字节的文件')
            body, metadata = normalize_markdown(decoded, title)
            metadata['source_label'] = '用户上传'
        except (UnicodeDecodeError, ValueError) as exc:
            raise HTTPException(422, detail={'code': 'invalid_markdown', 'message': str(exc)[:160]}) from exc
        if not manager.lock.acquire(blocking=False):
            raise HTTPException(409, detail={'code': 'index_busy', 'message': '索引正在处理，请稍后上传'})
        try:
            if store.state()['status'] == 'building':
                raise HTTPException(409, detail={'code': 'index_busy', 'message': '索引正在重建，请稍后上传'})
            if doc_id and not store.document(doc_id):
                raise HTTPException(404, detail={'code': 'document_not_found', 'message': '文档不存在'})
            file_id = uuid.uuid4().hex
            doc_id = doc_id or file_id
            upload_dir = settings.data_dir / 'uploads'
            upload_dir.mkdir(parents=True, exist_ok=True)
            (upload_dir / f'{file_id}.md').write_bytes(raw)
            doc = {'id': doc_id, 'title': metadata['title'], 'category': '用户上传', 'source_url': '',
                   'source_path': f'uploads/{file_id}.md',
                   'collected_at': datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
                   'version': 'user-upload', 'body': body, 'metadata': metadata}
            store.save_document(doc)
            return public_document(doc, 'stale')
        finally:
            manager.lock.release()

    @app.post('/api/documents', status_code=201)
    async def upload(file: UploadFile = File(...)):
        return await save_upload(file)

    @app.put('/api/documents/{doc_id}')
    async def update_document(doc_id: str, file: UploadFile = File(...)):
        # 按内部文档 ID 更新；同名 README 可以属于不同项目，不能按文件名覆盖。
        return await save_upload(file, doc_id)

    @app.post('/api/index/rebuild', status_code=202)
    def rebuild():
        if not store.documents():
            raise HTTPException(422, detail={'code': 'corpus_empty', 'message': '资料库为空，请先在资料库上传 Markdown 文档'})
        if not manager.lock.acquire(blocking=False):
            raise HTTPException(409, detail={'code': 'index_busy', 'message': '索引正在处理'})
        try:
            manager.begin()
        except IndexUnavailable as exc:
            raise HTTPException(409, detail={'code': 'index_busy', 'message': str(exc)}) from exc
        finally:
            manager.lock.release()
        def work():
            try:
                manager.rebuild(begun=True)
            except Exception:
                logging.getLogger(__name__).error('重建未完成，请查看服务端日志')
        threading.Thread(target=work, daemon=True).start()
        return {'status': 'building', 'message': '重建已开始，通过健康接口查询结果'}

    @app.post('/api/ask')
    def ask(payload: Question):
        if not store.documents():
            raise HTTPException(503, detail={'code': 'corpus_empty', 'message': '资料库为空，请先在资料库上传 Markdown 文档'})
        if store.state()['status'] != 'ready':
            raise HTTPException(503, detail={'code': 'index_unavailable', 'message': store.state()['message']})
        if not settings.llm_configured:
            raise HTTPException(503, detail={'code': 'model_not_configured',
                'message': '生成模型尚未配置。请在后端 .env 填写服务地址、密钥和模型名称；资料与检索评测仍可使用。'})
        try:
            return answer_question(payload.question, retriever, llm)
        except IndexUnavailable as exc:
            raise HTTPException(503, detail={'code': 'index_unavailable', 'message': str(exc)}) from exc
        except LLMError as exc:
            code = str(exc)
            raise HTTPException(502, detail={'code': code, 'message':
                '模型返回结构无效，请检查服务兼容性后重试' if code == 'invalid_model_output' else
                '模型服务请求失败，请检查后端配置与网络后重试'}) from exc
        except Exception as exc:
            logging.getLogger(__name__).exception('Retrieval failure')
            raise HTTPException(500, detail={'code': 'retrieval_failed', 'message': '检索运行失败，请查看服务端日志'}) from exc

    return app


app = create_app()

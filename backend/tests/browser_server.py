"""隔离的浏览器测试服务；使用真实检索、离线输出夹具，绝不作为默认问答服务。"""
from app.api import create_app
from app.answering import ModelAnswer, LLMError
from app.cli import import_snapshot
from app.config import ROOT, Settings
from app.indexing import IndexManager
from app.storage import Store


class OfflineBrowserClient:
    def answer(self, question, context):
        if question == '测试模型错误':
            raise LLMError('model_request_failed')
        if question == '测试无依据':
            return ModelAnswer(status='answered', answer='离线测试无效引用', citations=[{'ref': 999, 'quote': '不存在的证据'}])
        block = context[0]
        return ModelAnswer(status='answered',
            answer='**离线浏览器测试夹具，不是生成模型回答。**\n\n用于验证来源卡片与原文跳转。[1]',
            citations=[{'ref': 1, 'quote': block['text'][:180]}])


settings = Settings(_env_file=None, data_dir=ROOT/'.cache/browser-project-docs/runtime',
                    llm_base_url='https://offline.invalid/v1', llm_api_key='test-placeholder', llm_model='offline-browser-fixture')
store = Store(settings.data_dir/'metadata.sqlite3')
# 从空资料库开始，通过浏览器上传任意 Markdown 验证全流程。
app = create_app(settings, llm=OfflineBrowserClient())

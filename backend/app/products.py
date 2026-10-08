"""一个产品配置对应一套本地语料、示例问题和评测集，不参与检索算法。"""
import json
from pathlib import Path

from pydantic import BaseModel, Field, PrivateAttr


class Example(BaseModel):
    question: str
    doc_id: str
    quote: str = Field(min_length=1)


class Product(BaseModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9-]{0,47}$')
    name: str = Field(min_length=1)
    description: str
    source_label: str
    source_url: str = ''
    question_placeholder: str = '请输入你想了解的功能或操作步骤'
    corpus: str = 'corpus'
    evaluation: str | None = None
    examples: list[Example] = Field(default_factory=list)
    _directory: Path = PrivateAttr()

    def local_path(self, value: str) -> Path:
        path = (self._directory / value).resolve()
        if not path.is_relative_to(self._directory):
            raise ValueError('产品配置中的文件必须位于该产品目录内')
        return path

    @property
    def corpus_dir(self):
        return self.local_path(self.corpus)

    @property
    def dataset_path(self):
        return self.local_path(self.evaluation) if self.evaluation else None

    def public_info(self):
        return self.model_dump(include={'id', 'name', 'description', 'source_label',
                                        'source_url', 'question_placeholder'})


def load_product(path: Path) -> Product:
    product = Product.model_validate_json(path.read_text('utf-8'))
    product._directory = path.resolve().parent
    product.corpus_dir  # 启动时校验配置路径，而不是导入时才发现错误。
    product.dataset_path
    return product


def load_manifest(product: Product):
    path = product.corpus_dir / 'manifest.json'
    data = json.loads(path.read_text('utf-8'))
    if data['product_id'] != product.id:
        raise ValueError('语料清单的 product_id 与产品配置不一致')
    if len({doc['id'] for doc in data['documents']}) != len(data['documents']):
        raise ValueError('语料清单含重复文档 ID')
    return data

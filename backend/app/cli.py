import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from .config import ROOT, Settings
from .documents import read_markdown
from .indexing import IndexManager
from .products import load_manifest
from .storage import Store


def import_snapshot(store, settings=None):
    settings = settings or Settings()
    product = settings.product
    manifest = load_manifest(product)
    documents = []
    for item in manifest['documents']:
        path = (product.corpus_dir / item['snapshot_file']).resolve()
        if not path.is_relative_to(product.corpus_dir):
            raise ValueError('快照文件必须位于产品语料目录内')
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError(f"固定快照校验失败：{item['title']}")
        body, metadata = read_markdown(path)
        metadata['source_label'] = item.get('source_label', product.source_label)
        metadata['snapshot_product'] = product.id
        documents.append({**item, 'body': body, 'metadata': metadata})
    # 全部文件核对成功后才开始写入，校验失败不会部分更新。
    store.bind_product(product.id)
    store.replace_snapshot(documents, product.id)
    return len(manifest['documents'])


def prepare_manifest(settings):
    """把用户准备的 Markdown 生成清单；不抓取网站，不生成产品事实。"""
    product = settings.product
    directory = product.corpus_dir
    docs = []
    for path in sorted(directory.rglob('*.md')):
        if not path.resolve().is_relative_to(directory):
            raise ValueError('语料文件不能链接到产品目录外')
        _, meta = read_markdown(path)
        relative = path.relative_to(directory).as_posix()
        url = str(meta.get('source_url', product.source_url))
        if url and urlparse(url).scheme not in {'http', 'https'}:
            raise ValueError(f'{relative} 的来源链接必须使用 http 或 https')
        docs.append({'id': str(meta.get('doc_id') or product.id + '-' + hashlib.sha256(relative.encode()).hexdigest()[:12]),
                     'title': meta['title'], 'category': str(meta.get('category', '使用教程')),
                     'source_url': url, 'source_label': str(meta.get('source_label', product.source_label)),
                     'source_path': relative, 'snapshot_file': relative,
                     'collected_at': str(meta.get('collected_at', date.today().isoformat())),
                     'version': str(meta.get('version', 'local-snapshot')),
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    if not docs:
        raise ValueError('语料目录没有 Markdown，请先添加真实文档')
    if len({doc['id'] for doc in docs}) != len(docs):
        raise ValueError('Markdown 的 doc_id 有重复')
    commit = hashlib.sha256(json.dumps([(d['id'], d['sha256']) for d in docs]).encode()).hexdigest()
    manifest = {'product_id': product.id, 'product': product.name, 'commit': commit, 'documents': docs}
    (directory / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
    return len(docs)


def init_product(product_id, name):
    from .products import Product
    product = Product(id=product_id, name=name, description=f'根据本地教程查找{name}的功能和操作步骤。',
                      source_label='用户提供的教程')
    directory = ROOT / 'products' / product_id
    if directory.exists():
        raise ValueError('产品目录已存在，不覆盖已有资料')
    (directory / 'corpus').mkdir(parents=True)
    (directory / 'product.json').write_text(product.model_dump_json(indent=2), 'utf-8')
    (directory / 'README.md').write_text('将有权使用的 UTF-8 Markdown 放入 corpus；配置来源和示例问题后执行 prepare、import、index。\n', 'utf-8')
    return directory


def main():
    parser = argparse.ArgumentParser(description='帮助中心本地资料与索引管理')
    parser.add_argument('command', choices=['init-product', 'prepare', 'import', 'index', 'status'])
    parser.add_argument('--id', help='新产品的目录 ID，例如 qq')
    parser.add_argument('--name', help='新产品的显示名称，例如 QQ')
    args = parser.parse_args()
    if args.command == 'init-product':
        if not args.id or not args.name:
            parser.error('init-product 需要 --id 和 --name')
        print(init_product(args.id, args.name))
        return
    settings = Settings()
    if args.command == 'prepare':
        print(f'已为 {settings.product.name} 生成 {prepare_manifest(settings)} 篇文档的清单。')
        return
    store = Store(settings.data_dir / 'metadata.sqlite3')
    store.bind_product(settings.product.id)
    if args.command == 'import':
        print(f'已导入 {settings.product.name} 的 {import_snapshot(store, settings)} 篇固定文档。请运行 index。')
    elif args.command == 'index':
        print(json.dumps(IndexManager(store, settings).rebuild(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(store.state(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

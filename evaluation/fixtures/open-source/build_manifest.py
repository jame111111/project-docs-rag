"""仅为测试夹具生成来源清单；源文件逐字保留，不被正式应用自动导入。"""
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    source = json.loads((root/'source.json').read_text('utf-8'))
    documents = []
    for filename in source['files']:
        path = root/'corpus'/filename
        documents.append({
            'id': 'fixture-' + hashlib.sha256(filename.encode()).hexdigest()[:12],
            'title': filename,
            'category': '固定测试文档',
            'source_url': f"{source['repository']}/blob/{source['commit']}/{filename}",
            'source_label': '上游原文（仅测试）',
            'source_path': filename, 'snapshot_file': filename,
            'collected_at': source['collected_at'], 'version': source['commit'],
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    manifest = {'product_id': 'open-source-fixture', 'product': '开源项目文档测试集',
                'commit': source['commit'], 'documents': documents}
    (root/'corpus/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
    print(f"固定测试来源：{len(documents)} 篇，提交 {source['commit']}")


if __name__ == '__main__':
    main()

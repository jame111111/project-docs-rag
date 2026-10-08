"""将人工编写的问题和证据冻结成真实正文区间，不根据检索结果调题。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import Settings
from app.documents import read_markdown
from app.products import load_manifest
from app.chunking import section_spans


def freeze(settings):
    product = settings.product
    target = product.dataset_path
    if not target:
        raise ValueError('请先在产品配置的 evaluation 字段指定题集输出路径')
    specs = json.loads((target.parent / 'questions.json').read_text('utf-8'))
    manifest = load_manifest(product)
    bodies = {d['id']: read_markdown(product.corpus_dir / d['snapshot_file'])[0] for d in manifest['documents']}
    questions = specs['questions']
    if len({q['id'] for q in questions}) != len(questions):
        raise ValueError('问题 ID 重复')
    for q in questions:
        if bool(q['evidence']) != q['answerable']:
            raise ValueError(f"{q['id']} 的可回答状态与证据不一致")
        for e in q['evidence']:
            body = bodies[e['doc_id']]
            quote = e['quote']
            if not quote:
                raise ValueError('证据不能为空')
            offsets = [i for i in range(len(body)) if body.startswith(quote, i)]
            occurrence = e.pop('occurrence', None)
            if not offsets or (len(offsets) > 1 and occurrence is None):
                raise ValueError(f"{q['id']} 的证据缺失或重复；重复时明确 occurrence（从 0 开始）")
            e['start'] = offsets[occurrence or 0]
            e['end'] = e['start'] + len(quote)
            e['section'] = next((s[2] for s in section_spans(body) if s[0] <= e['start'] < s[1]), '')
    data = {'version': 2, 'product_id': product.id, 'corpus_commit': manifest['commit'],
            'offset_unit': 'unicode_codepoint', 'questions': questions,
            'notes': '参考要点和证据由人工编写；本脚本只定位正文。最终题在配置冻结后运行，不按最终题调参。'}
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
    print(target, hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=ROOT/'evaluation/fixtures/open-source/profile.json')
    args = parser.parse_args()
    freeze(Settings(product_config=args.config))

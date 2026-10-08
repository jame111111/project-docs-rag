"""冻结20×30题与原文偏移。题目定义只在 evaluation 中，不进入业务代码。"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
from app.documents import read_markdown
from app.chunking import section_spans
from evaluation.github_readmes.curated import FACTS, NEGATIVES

SUITE = ROOT / 'evaluation/github_readmes'


def build():
    selection = json.loads((SUITE / 'selection.json').read_text('utf-8'))['projects']
    if {p['id'] for p in selection} != set(FACTS) or set(FACTS) != set(NEGATIVES):
        raise ValueError('选择清单与题目项目不一致')
    inventory = []
    for project in selection:
        pid = project['id']
        if len(FACTS[pid]) != 12 or len(NEGATIVES[pid]) != 6:
            raise ValueError(pid + ' 不是12组事实与6道无依据题')
        directory = SUITE / 'projects' / pid
        source = json.loads((directory / 'source.json').read_text('utf-8'))
        raw_path = directory / 'corpus/README.md'
        if hashlib.sha256(raw_path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError(pid + ' README原始字节校验失败')
        body, _ = read_markdown(raw_path)
        spans = list(section_spans(body))
        questions = []
        for index, (direct, colloquial, answer, quotes) in enumerate(FACTS[pid]):
            evidence = []
            for quote in quotes:
                offsets = [i for i in range(len(body)) if body.startswith(quote, i)]
                if len(offsets) != 1:
                    raise ValueError(f'{pid} fact{index+1}: 证据出现{len(offsets)}次，必须显式消歧：{quote}')
                start = offsets[0]
                evidence.append({'doc_id': 'readme-' + pid + '-doc', 'quote': quote,
                                 'start': start, 'end': start + len(quote),
                                 'section': next((s[2] for s in spans if s[0] <= start < s[1]), '')})
            for kind, question in [('direct', direct), ('colloquial', colloquial)]:
                questions.append({'id': f'{pid}-Q{len(questions)+1:02}', 'question': question,
                    'answerable': True, 'split': 'dev' if index < 9 else 'final', 'kind': kind,
                    'fact_group': f'{pid}-F{index+1:02}', 'reference_points': [answer], 'evidence': evidence})
        for index, question in enumerate(NEGATIVES[pid]):
            questions.append({'id': f'{pid}-Q{len(questions)+1:02}', 'question': question,
                'answerable': False, 'split': 'dev' if index < 4 else 'final', 'kind': 'unsupported',
                'fact_group': None, 'reference_points': ['当前 README 缺少该题要求的完整细节或用户环境证据，应明确依据不足。'],
                'evidence': [], 'negative_basis': '只检查本地根目录 README；未采集链接指向的文档，不代表产品不支持该能力。'})
        if len({q['question'] for q in questions}) != 30:
            raise ValueError(pid + ' 题目数量或唯一性错误')
        dataset = {'version': 3, 'product_id': 'readme-' + pid, 'corpus_commit': source['commit'],
            'offset_unit': 'unicode_codepoint', 'questions': questions,
            'notes': '依据已读取快照编写；原文位置自动校验；独立人工复核待完成。两种措辞共享事实，事实组不跨开发/最终集；未按检索结果改题。'}
        target = directory / 'evaluation/dataset.json'
        target.parent.mkdir(exist_ok=True)
        data = json.dumps(dataset, ensure_ascii=False, indent=2)
        target.write_text(data, 'utf-8')
        inventory.append({'project': pid, 'questions': 30, 'answerable': 24, 'unanswerable': 6,
                          'distinct_positive_fact_groups': 12,
                          'dataset_sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    (SUITE / 'datasets.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), 'utf-8')
    print('已冻结20份README、600题、480正例、120无依据题；最终集每项目8题，证据与偏移已核对。')


if __name__ == '__main__':
    build()

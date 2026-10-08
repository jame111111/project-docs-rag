"""真实模型逐题生成与人工核对表。未核对数据不会转换成正确率。"""
import argparse
import json
from pathlib import Path

from app.answering import LLMClient, answer_question
from .common import MODES, output_dir, setup, write_csv, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['dev', 'final', 'all'], default='dev')
    parser.add_argument('--config', type=Path, help='独立测试资料配置，不影响默认应用')
    parser.add_argument('--data-dir', type=Path, help='独立评测运行目录')
    args = parser.parse_args()
    settings, _, _, retriever, questions, meta = setup(args.split, args.config, args.data_dir)
    out = output_dir('answers')
    meta['llm_model'] = settings.llm_model or 'not_configured'
    rows, compact = [], []
    for q in questions:
        for mode in MODES:
            for top_k in [1, 5]:
                row = {'id': q['id'], 'question': q['question'], 'answerable': q['answerable'],
                       'mode': mode, 'top_k': top_k, 'reference_points': q['reference_points'],
                       'evidence': q['evidence'], 'review': 'unverified', 'review_notes': ''}
                if not settings.llm_configured:
                    row.update(run_status='not_run', reason='model_not_configured', answer='', citations=[])
                else:
                    try:
                        response = answer_question(q['question'], retriever, LLMClient(settings), mode, top_k)
                        row.update(run_status='generated', **response)
                    except Exception as exc:
                        row.update(run_status='error', reason=type(exc).__name__, answer='', citations=[])
                rows.append(row)
                compact.append({k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for k, v in row.items()
                                if k not in ['evidence', 'timings']})
                # 每条写入，运行中断仍保留已生成结果，不覆盖以前的运行。
                write_json(out/'results.json', {'metadata': meta, 'results': rows,
                    'answer_accuracy': 'unverified', 'false_refusal_rate': 'unverified', 'correct_refusal_rate': 'unverified'})
                write_csv(out/'review.csv', compact)
    print(out)
    print('生成状态和人工核对状态分别保存；只有人工填写 review 后才能统计。')


if __name__ == '__main__':
    main()

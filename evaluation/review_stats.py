import argparse
import csv
import json
from pathlib import Path
from .common import write_json


def main():
    parser = argparse.ArgumentParser(description='统计已人工核对的结果；review 可填 correct/incorrect/false_refusal/correct_refusal')
    parser.add_argument('csv', type=Path)
    args = parser.parse_args()
    rows = list(csv.DictReader(args.csv.open(encoding='utf-8-sig')))
    groups = {}
    for row in rows:
        key = row['mode'] + ':top_k=' + row['top_k']
        group = groups.setdefault(key, {'reviewed': 0, 'unverified': 0, 'correct': 0, 'incorrect': 0,
                                       'false_refusal': 0, 'correct_refusal': 0,
                                       'positive_reviewed': 0, 'negative_reviewed': 0})
        if row['run_status'] != 'generated' or row['review'] not in ['correct', 'incorrect', 'false_refusal', 'correct_refusal']:
            group['unverified'] += 1
            continue
        group['reviewed'] += 1
        group[row['review']] += 1
        group['positive_reviewed' if row['answerable'].lower() == 'true' else 'negative_reviewed'] += 1
    for group in groups.values():
        group['accuracy_on_reviewed'] = (group['correct'] + group['correct_refusal']) / group['reviewed'] if group['reviewed'] else 'unverified'
        group['answer_accuracy_on_reviewed_positives'] = group['correct']/group['positive_reviewed'] if group['positive_reviewed'] else 'unverified'
        group['false_refusal_rate_on_reviewed_positives'] = group['false_refusal']/group['positive_reviewed'] if group['positive_reviewed'] else 'unverified'
        group['correct_refusal_rate_on_reviewed_negatives'] = group['correct_refusal']/group['negative_reviewed'] if group['negative_reviewed'] else 'unverified'
    output = args.csv.parent / ('review-summary-' + __import__('uuid').uuid4().hex[:6] + '.json')
    write_json(output, groups)
    print(output)


if __name__ == '__main__':
    main()

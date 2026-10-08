"""只下载公开根目录 README 与许可文件，固定提交；不运行上游代码。"""
import argparse
import hashlib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / 'evaluation/github_readmes'


def fetch(url):
    with urlopen(Request(url, headers={'User-Agent': 'local-readme-rag-evaluation',
                                      'Accept': 'application/vnd.github+json'}), timeout=45) as response:
        return response.read()


def snapshot(project):
    directory = SUITE / 'projects' / project['id']
    if (directory / 'source.json').exists():
        return json.loads((directory / 'source.json').read_text('utf-8'))
    repository = project['repository']
    # GitHub 网页的 currentOid 是当前默认分支提交；无需匿名 API 配额。
    page = fetch('https://github.com/' + repository).decode('utf-8')
    match = re.search(r'"currentOid":"([0-9a-f]{40})"', page)
    if match:
        commit = match[1]
    else:
        remote = subprocess.check_output(['git', 'ls-remote', 'https://github.com/' + repository + '.git', 'HEAD'],
                                         timeout=60, text=True)
        commit = remote.split()[0]
    if len(commit) != 40:
        raise ValueError('无法确认完整提交号')
    raw_prefix = f'https://raw.githubusercontent.com/{repository}/{commit}/'
    readme_path = None
    for candidate in ['README.md', 'readme.md', 'Readme.md']:
        try:
            readme = fetch(raw_prefix + candidate)
            readme.decode('utf-8-sig')
            readme_path = candidate
            break
        except HTTPError as exc:
            if exc.code != 404:
                raise
    if not readme_path:
        raise ValueError('根目录不存在 UTF-8 Markdown README；不会转换其他格式')
    licenses = []
    for candidate in ['LICENSE', 'LICENSE.txt', 'LICENSE.md', 'COPYING', 'NOTICE', 'NOTICE.txt']:
        try:
            raw = fetch(raw_prefix + candidate)
            raw.decode('utf-8-sig')
            licenses.append((candidate, raw))
        except HTTPError as exc:
            if exc.code != 404:
                raise
    license_text = '\n'.join(raw.decode('utf-8-sig') for name, raw in licenses if 'NOTICE' not in name)
    if re.search(r'Apache License\s+Version 2\.0', license_text, re.I):
        spdx = 'Apache-2.0'
    elif 'GNU AFFERO GENERAL PUBLIC LICENSE' in license_text:
        spdx = 'AGPL-3.0 (see upstream terms)'
    elif 'Permission is hereby granted, free of charge' in license_text:
        spdx = 'MIT'
    elif 'Redistribution and use in source and binary forms' in license_text:
        spdx = 'BSD-style (see full upstream license)'
    else:
        raise ValueError('许可未确认；保留失败记录，不把未确认来源加入测试')
    (directory / 'corpus').mkdir(parents=True, exist_ok=True)
    (directory / 'licenses').mkdir(exist_ok=True)
    (directory / 'corpus/README.md').write_bytes(readme)
    for filename, raw in licenses:
        (directory / 'licenses' / filename).write_bytes(raw)
    source = {**project, 'repository_url': 'https://github.com/' + repository,
              'commit': commit, 'source_path': readme_path,
              'source_url': f'https://github.com/{repository}/blob/{commit}/{readme_path}',
              'collected_at': datetime.now(timezone.utc).isoformat(),
              'license_spdx': spdx,
              'license_files': [filename for filename, _ in licenses],
              'sha256': hashlib.sha256(readme).hexdigest(), 'bytes': len(readme)}
    (directory / 'source.json').write_text(json.dumps(source, ensure_ascii=False, indent=2), 'utf-8')
    product_id = 'readme-' + project['id']
    profile = {'id': product_id, 'name': repository + ' README 测试', 'description': '独立 README 测试快照',
               'source_label': 'GitHub 固定提交的根目录 README', 'source_url': source['source_url'],
               'corpus': 'corpus', 'evaluation': 'evaluation/dataset.json', 'examples': []}
    (directory / 'profile.json').write_text(json.dumps(profile, ensure_ascii=False, indent=2), 'utf-8')
    manifest = {'product_id': product_id, 'product': profile['name'], 'commit': commit,
                'documents': [{'id': product_id + '-doc', 'title': repository + ' README',
                'category': project['category'], 'source_url': source['source_url'], 'source_path': readme_path,
                'snapshot_file': 'README.md', 'collected_at': source['collected_at'], 'version': commit,
                'sha256': source['sha256']}]}
    (directory / 'corpus/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
    return source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    projects = json.loads((SUITE / 'selection.json').read_text('utf-8'))['projects']
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(snapshot, project): project for project in projects}
        for future in as_completed(futures):
            project = futures[future]
            try:
                source = future.result()
                results.append(source)
                print(project['id'], source['bytes'], source['commit'], source['license_spdx'], flush=True)
            except Exception as exc:
                errors.append({'project': project['id'], 'error_type': type(exc).__name__, 'message': str(exc)})
                print(project['id'], type(exc).__name__, flush=True)
    (SUITE / 'sources.json').write_text(json.dumps({'sources': sorted(results, key=lambda x: x['id']),
                                                  'errors': errors}, ensure_ascii=False, indent=2), 'utf-8')
    if errors:
        raise SystemExit(f'{len(errors)} 个来源未采集成功，见 sources.json；没有生成替代文档。')


if __name__ == '__main__':
    main()

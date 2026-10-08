"""只负责 Markdown 读取与规范化。所有偏移以规范化正文的 Python 字符为单位。"""
import re
import json
from pathlib import Path

import yaml


def normalize_markdown(raw: str, fallback_title: str) -> tuple[str, dict]:
    raw = raw.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    metadata = {}
    if raw.startswith('---\n'):
        match = re.match(r'^---\n(.*?)\n---(?:\n|$)', raw, re.S)
        if not match:
            raise ValueError('front matter 未闭合')
        try:
            metadata = yaml.safe_load(match[1]) or {}
        except yaml.YAMLError as exc:
            raise ValueError('front matter 的 YAML 格式无效') from exc
        if not isinstance(metadata, dict):
            raise ValueError('front matter 必须是键值对象')
        # YAML 会把未加引号的日期解析成 date；保存为可传输的 JSON 元数据。
        metadata = json.loads(json.dumps(metadata, ensure_ascii=False, default=str))
        raw = raw[match.end():]

    # 代码中的双链是语法示例，保持原样；正文保留别名显示文字。
    parts = re.split(r'(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)', raw)
    for i in range(0, len(parts), 2):
        def readable(m: re.Match) -> str:
            target = m[2]
            display = target.split('|', 1)[-1] if '|' in target else target.split('/')[-1]
            return f'[图片：{display}]' if m[1] else display
        parts[i] = re.sub(r'(!?)\[\[([^\]]+)\]\]', readable, parts[i])
    body = ''.join(parts).strip() + '\n'
    if not body.strip():
        raise ValueError('Markdown 正文为空')
    heading = re.search(r'^#\s+(.+)$', '\n'.join(parts[::2]), re.M)
    metadata['title'] = str(metadata.get('title') or (heading[1] if heading else fallback_title))
    return body, metadata


def read_markdown(path: Path) -> tuple[str, dict]:
    return normalize_markdown(path.read_text(encoding='utf-8-sig'), path.stem)

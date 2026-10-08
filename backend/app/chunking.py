"""结构化父块与带重叠的子块；用区间运算定位，禁止 find(文本) 反查位置。"""
import re
from dataclasses import dataclass


@dataclass
class Chunk:
    id: str
    doc_id: str
    parent_id: str | None
    section: str
    start: int
    end: int
    text: str


def section_spans(body: str):
    start, path, fence = 0, [], None
    for m in re.finditer(r'.*(?:\n|$)', body):
        line = m[0]
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
            continue
        heading = re.match(r'^(#{1,6})\s+(.+?)\s*#*\s*$', line.strip('\n'))
        if heading and fence is None:
            if m.start() > start:
                yield start, m.start(), ' / '.join(t for _, t in path) or '正文'
            level = len(heading[1])
            path = [(n, t) for n, t in path if n < level] + [(level, heading[2])]
            start = m.start()
    if start < len(body):
        yield start, len(body), ' / '.join(t for _, t in path) or '正文'


def paragraph_ends(text: str) -> list[int]:
    # fenced code 中的空行不作为父块切点；步骤列表整体保持在一个段落。
    ends, fence = [], None
    for m in re.finditer(r'.*(?:\n|$)', text):
        marker = re.match(r'^\s*(`{3,}|~{3,})', m[0])
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
        if not m[0].strip() and fence is None and m.end() > 0:
            ends.append(m.end())
    return sorted(set(ends + [len(text)]))


def chunk_document(doc_id: str, body: str, parent_target=800, child_target=200, overlap=40):
    if not 0 <= overlap < child_target:
        raise ValueError('overlap 必须小于 child_target')
    parents, children = [], []
    for section_start, section_end, section in section_spans(body):
        pstart = section_start
        pending = section_start
        for relative_end in paragraph_ends(body[section_start:section_end]):
            end = section_start + relative_end
            if end - pstart > parent_target and pending > pstart:
                parents.append(Chunk(f'{doc_id}:p{len(parents)}', doc_id, None, section,
                                     pstart, pending, body[pstart:pending]))
                pstart = pending
            pending = end
        if pending > pstart:
            parents.append(Chunk(f'{doc_id}:p{len(parents)}', doc_id, None, section,
                                 pstart, pending, body[pstart:pending]))
    for parent in parents:
        text = parent.text
        # 句子/换行/段落优先；单个超长句子保持完整，允许超过目标。
        boundaries = sorted(set([m.end() for m in re.finditer(r'[。！？!?](?:[”’])?|\n', text)] + [len(text)]))
        start, previous_end = 0, 0
        while start < len(text):
            candidates = [b for b in boundaries if b > previous_end]
            near = [b for b in candidates if b - start <= child_target + 50]
            end = min(near, key=lambda b: abs(b - start - child_target)) if near else candidates[0]
            absolute_start, absolute_end = parent.start + start, parent.start + end
            children.append(Chunk(f'{doc_id}:c{len(children)}', doc_id, parent.id, parent.section,
                                  absolute_start, absolute_end, body[absolute_start:absolute_end]))
            if end == len(text):
                break
            # 区间直接回退 40 字，重叠保持真实原文，不跨父块。
            start = max(start + 1, end - overlap)
            previous_end = end
    return parents, children

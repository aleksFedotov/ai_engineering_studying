#!/usr/bin/env python3
"""Convert Day39 human annotations in review.md to validated JSONL.

Usage: python convert_labels.py review.md labeled_examples.jsonl
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HEAD = re.compile(r'^## (example_\d+)\s*$', re.M)
FIELDS = [
    ('question', r'\*\*Вопрос\*\*'),
    ('answer', r'\*\*Ответ системы\*\*'),
    ('reference', r'\*\*Рабочий эталон — проверь по контексту\*\*'),
    ('label', r'\*\*Вердикт\*\*:'),
    ('critique', r'\*\*Критика\*\*:'),
    ('reference_issue', r'\*\*Проблема эталона\*\*:'),
]
MARKER = re.compile('|'.join(f'(?P<{key}>{pat})' for key, pat in FIELDS))


def parse_block(example_id, block):
    errors = []
    # Metadata and retrieved context are not part of the expert annotation.
    visible = re.split(r'<details\b', block, maxsplit=1, flags=re.I)[0]
    group = re.search(r'^Группа вопроса:\s*`([^`]+)`', visible, re.M)
    if not group:
        errors.append(f'{example_id}: отсутствует группа вопроса')
    matches = list(MARKER.finditer(visible))
    sections = {}
    for i, match in enumerate(matches):
        key = match.lastgroup
        value = visible[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(visible)].strip()
        if key in sections:
            errors.append(f'{example_id}: повторное поле {key}')
        sections[key] = value
    for key in ('question', 'answer', 'reference', 'label', 'critique'):
        if not sections.get(key):
            errors.append(f'{example_id}: пустое или отсутствующее поле {key}')
    label = sections.get('label', '').upper()
    if label not in ('PASS', 'FAIL'):
        errors.append(f'{example_id}: недопустимый вердикт {label!r}')
    record = {
        'id': example_id,
        'question_group': group.group(1) if group else None,
        'question': sections.get('question', ''),
        'generated_answer': sections.get('answer', ''),
        'golden_answer': sections.get('reference', ''),
        'human_label': label,
        'human_critique': sections.get('critique', ''),
        'reference_issue': sections.get('reference_issue', ''),
    }
    return record, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', default='review.md')
    parser.add_argument('output', nargs='?', default='labeled_examples.jsonl')
    parser.add_argument('--expected', type=int, default=49)
    args = parser.parse_args()
    text = Path(args.input).read_text(encoding='utf-8-sig')
    matches = list(HEAD.finditer(text))
    errors, records = [], []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        record, issues = parse_block(match.group(1), text[match.end():end])
        records.append(record)
        errors.extend(issues)
    ids = [r['id'] for r in records]
    for duplicate, n in Counter(ids).items():
        if n > 1:
            errors.append(f'Повтор ID: {duplicate} ({n} раз)')
    if len(records) != args.expected:
        errors.append(f'Ожидалось {args.expected} записей, найдено {len(records)}')
    expected_ids = {f'example_{i:03d}' for i in range(1, args.expected + 1)}
    if set(ids) != expected_ids:
        errors.append(f'Несовпадение ID: отсутствуют {sorted(expected_ids-set(ids))}; лишние {sorted(set(ids)-expected_ids)}')
    labels = Counter(r['human_label'] for r in records)
    print(f'Записей: {len(records)}; PASS: {labels["PASS"]}; FAIL: {labels["FAIL"]}')
    if errors:
        print('Проверка НЕ ПРОЙДЕНА:', file=sys.stderr)
        for err in errors:
            print(' -', err, file=sys.stderr)
        print('JSONL не записан. Исправьте review.md и повторите.', file=sys.stderr)
        return 1
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    # Independent check that JSONL can be decoded.
    with target.open(encoding='utf-8') as f:
        assert sum(1 for line in f if json.loads(line)) == len(records)
    print(f'Проверка пройдена. Создан: {target}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

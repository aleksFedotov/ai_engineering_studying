#!/usr/bin/env python3
"""Group-safe train/dev/test split for human-labeled LLM-as-a-Judge examples.

No external dependencies. The same question_group never appears in two splits.
The search approximates requested proportions while retaining PASS and FAIL
in every split, if that is feasible.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import random
import sys

SPLITS = ('train', 'dev', 'test')
RATIOS = (0.60, 0.20, 0.20)
LABELS = {'PASS', 'FAIL'}


def load(path):
    rows = []
    ids = set()
    with path.open(encoding='utf-8-sig') as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f'Строка {line_no}: некорректный JSON: {exc}') from exc
            if not isinstance(row, dict):
                raise ValueError(f'Строка {line_no}: ожидается JSON-объект')
            for key in ('id', 'question_group', 'question', 'generated_answer',
                        'golden_answer', 'human_label', 'human_critique'):
                if not isinstance(row.get(key), str) or not row[key].strip():
                    raise ValueError(f'Строка {line_no}: отсутствует поле {key!r}')
            row['human_label'] = row['human_label'].strip().upper()
            if row['human_label'] not in LABELS:
                raise ValueError(f'Строка {line_no}: неизвестная метка {row["human_label"]!r}')
            if row['id'] in ids:
                raise ValueError(f'Строка {line_no}: повторяется id={row["id"]!r}')
            ids.add(row['id'])
            rows.append(row)
    if not rows:
        raise ValueError('Входной файл пуст')
    return rows


def split_groups(rows, seed, trials):
    groups = defaultdict(list)
    for row in rows:
        groups[row['question_group']].append(row)
    if len(groups) < 3:
        raise ValueError('Для трёх выборок нужны хотя бы три группы вопросов')
    fail_groups = sum(any(r['human_label'] == 'FAIL' for r in group)
                      for group in groups.values())
    pass_groups = sum(any(r['human_label'] == 'PASS' for r in group)
                      for group in groups.values())
    if fail_groups < 3 or pass_groups < 3:
        raise ValueError('Невозможно иметь оба класса в каждой выборке: '
                         f'групп с FAIL={fail_groups}, с PASS={pass_groups}; нужно >=3')

    rng = random.Random(seed)
    keys = list(groups)
    total = len(rows)
    total_fail = sum(r['human_label'] == 'FAIL' for r in rows)
    targets = [total * p for p in RATIOS]
    target_fails = [total_fail * p for p in RATIOS]
    best_score = float('inf')
    best = None

    # Monte Carlo search over group assignments. Reproducible for a given seed.
    for _ in range(trials):
        assignment = [rng.choices(range(3), weights=RATIOS)[0] for _ in keys]
        sizes = [0, 0, 0]
        fails = [0, 0, 0]
        passes = [0, 0, 0]
        for key, part in zip(keys, assignment):
            g = groups[key]
            sizes[part] += len(g)
            nfail = sum(r['human_label'] == 'FAIL' for r in g)
            fails[part] += nfail
            passes[part] += len(g) - nfail
        if any(not (fails[i] and passes[i]) for i in range(3)):
            continue
        # Row counts are primary, FAIL distribution secondary.
        score = sum(((sizes[i] - targets[i]) / total) ** 2 for i in range(3))
        score += 1.5 * sum(((fails[i] - target_fails[i]) / total_fail) ** 2
                           for i in range(3))
        if score < best_score:
            best_score = score
            best = dict(zip(keys, assignment))
    if best is None:
        raise ValueError('Не найдено допустимое разбиение. Увеличь --trials '
                         'или пересмотри ограничения.')

    parts = {name: [] for name in SPLITS}
    for row in rows:
        parts[SPLITS[best[row['question_group']]]].append(row)
    # Verify no overlap of IDs and question groups.
    for i, a in enumerate(SPLITS):
        for b in SPLITS[i + 1:]:
            assert {r['id'] for r in parts[a]}.isdisjoint(r['id'] for r in parts[b])
            assert {r['question_group'] for r in parts[a]}.isdisjoint(
                r['question_group'] for r in parts[b])
    assert sum(map(len, parts.values())) == len(rows)
    return parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Путь к labeled_examples.jsonl')
    parser.add_argument('--out-dir', type=Path, default=Path('splits'))
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--trials', type=int, default=100000,
                        help='Число попыток поиска группового разбиения')
    args = parser.parse_args()
    if args.trials < 1:
        parser.error('--trials должен быть положительным')
    try:
        rows = load(args.input)
        parts = split_groups(rows, args.seed, args.trials)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for name, examples in parts.items():
            path = args.out_dir / f'{name}.jsonl'
            with path.open('w', encoding='utf-8') as f:
                for example in examples:
                    f.write(json.dumps(example, ensure_ascii=False) + '\n')
        print(f'Всего: {len(rows)} записей; '
              f'{len(set(r["question_group"] for r in rows))} групп')
        for name, examples in parts.items():
            counts = Counter(r['human_label'] for r in examples)
            print(f'{name:5s}: {len(examples):2d} записей '
                  f'({len(examples)/len(rows):.1%}); '
                  f'PASS={counts["PASS"]}, FAIL={counts["FAIL"]}; '
                  f'групп={len(set(r["question_group"] for r in examples))}')
        print('Проверка пересечений ID и question_group: OK')
        print(f'Файлы: {args.out_dir.resolve()}')
    except (OSError, ValueError) as exc:
        print(f'Ошибка: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

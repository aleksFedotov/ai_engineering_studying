# День 40 — Регрессионное тестирование LLM: Promptfoo и CI/CD

> **Статус:** теория по трём источникам разобрана; практическая контрольная точка ещё не выполнена.  
> **Цель:** научиться обнаруживать ухудшение поведения LLM/RAG после изменений промпта или модели **до** попадания изменений в production.

## Источники

1. [Promptfoo — Getting Started](https://www.promptfoo.dev/docs/getting-started/) — базовая конфигурация, запуск, assertions, сравнение моделей и промптов.
2. [Promptfoo Tutorial — DataCamp](https://www.datacamp.com/tutorial/promptfoo-tutorial) — `defaultTest`, Python assertions, веса, повторные прогоны, кэш и GitHub Actions.
3. [Testing LLM Prompts Like Code: Regression Evals in CI/CD — Medium](https://medium.com/@alexrodriguesj/testing-llm-prompts-like-code-regression-evals-in-ci-cd-with-promptfoo-5242b4dcb9be) — silent regressions, baseline, JUnit XML, pass-rate gate и сравнение до/после.

Этот конспект обобщает разбор источников в нашем занятии; пояснения и примерные конфигурации адаптированы для RAG-проекта и не являются дословными фрагментами статей.

## 1. Ключевые понятия

| Термин | Суть |
|---|---|
| **Evaluation (оценка)** | Проверка качества системы на наборе примеров. |
| **Regression testing (регрессионное тестирование)** | Проверка, не ухудшилось ли поведение после изменения. |
| **Silent regression (незаметная регрессия)** | Исправление одного сценария ломает другие, но это замечают только пользователи. |
| **Test suite (тестовый набор)** | Набор вопросов, контекстов и критериев проверки. |
| **Assertion (проверяемое условие)** | Автоматическое требование к ответу или выполнению. |
| **Baseline (базовая версия)** | Результаты версии, с которой сравнивается новая версия (candidate). |
| **CI-gate (барьер непрерывной интеграции)** | Проверка, не позволяющая принять изменения при нарушении требований. |
| **Pass rate (доля успешных тестов)** | Процент прошедших тестов. |
| **Hard gate (обязательная проверка)** | Условие, провал которого недопустим независимо от общего процента. |

**Главный принцип:** промпт влияет на production-поведение так же, как код, поэтому изменения промпта должны проходить version control, review и автоматические тесты.

## 2. Как устроен Promptfoo

Поток: `prompts + providers + tests → promptfoo eval → assertions → PASS/FAIL → отчёт`.

- **`prompts`** — варианты инструкций и шаблонов с переменными `{{question}}`, `{{context}}`.
- **`providers`** — LLM API, локальные модели или собственная вызываемая система.
- **`tests`** — тестовые входы (`vars`) и ожидаемое поведение (`assert`).
- **`defaultTest`** — общие проверки для всех тестовых случаев.

### Команды

```bash
# Пример проекта
npx promptfoo@latest init --example getting-started

# Запуск тестов
npx promptfoo@latest eval

# Просмотр результатов
npx promptfoo@latest view

# Несколько повторов (для изучения вариативности)
npx promptfoo@latest eval --repeat 3 --no-cache
```

Для CI лучше закрепить версию Promptfoo вместо постоянного `@latest`. Для API-провайдеров нужны ключи, передаваемые через переменные окружения или секреты CI.

## 3. Пример `promptfooconfig.yaml` для RAG

Учебная конфигурация для проверки **генератора с фиксированным контекстом**:

```yaml
description: RAG regression tests

prompts:
  - |
    Answer using only the provided context.
    If the context is insufficient, say so.
    Context: {{context}}
    Question: {{question}}

providers:
  - openai:gpt-4.1-mini  # пример: проверь доступность модели и ключа

defaultTest:
  assert:
    - type: latency
      threshold: 10000

tests:
  - vars:
      question: "What is overfitting?"
      context: >
        Overfitting occurs when a model learns training data
        too closely and generalizes poorly to unseen data.
    assert:
      - type: llm-rubric
        value: >
          The answer must explain that overfitting
          harms generalization to unseen data.

  - vars:
      question: "Who invented Python?"
      context: "Python is a high-level programming language."
    assert:
      - type: llm-rubric
        value: >
          The answer must say that the provided context
          does not contain the requested information.
```

**Ограничение:** фиксированный `context` тестирует в основном генерацию. Чтобы проверять изменения chunking, retrieval, reranking и `top_k`, нужно вызывать весь RAG-пайплайн через custom provider.

## 4. Виды assertions

| Проверка | Применение | Ограничение |
|---|---|---|
| `contains`, `icontains` | Наличие строки | Не проверяют смысл; возможны ложные FAIL. |
| `not-contains` | Отсутствие запрещённой строки | Не ловит перефразирование. |
| `regex` | Формат ответа | Нужно корректное регулярное выражение. |
| `llm-rubric` | Смысловая корректность | Судья может ошибаться и быть недетерминированным. |
| `python` | Собственная проверка | Нужно написать и поддерживать код. |
| `latency`, `cost` | Задержка и стоимость | Оценивают завершённый запрос, а не ограничивают его заранее. |

### Пример Python assertion

```python
# evals/assert_length.py

def get_assert(output, context):
    words = len(output.split())
    ok = 50 <= words <= 200
    return {
        "pass": ok,
        "score": 1.0 if ok else 0.0,
        "reason": f"Word count: {words}; expected 50..200",
    }
```

```yaml
assert:
  - type: python
    value: file://evals/assert_length.py
```

Проверки формата (например, обязательный JSON с `answer` и `sources`) полезно делать детерминированными: семантически правильный, но невалидный JSON может сломать приложение.

## 5. Взвешенные оценки и pass rate — не одно и то же

Для **одного теста** взвешенная оценка (weighted score):

\[
S = \frac{\sum_i w_i s_i}{\sum_i w_i}
\]

где `w_i` — вес assertion, `s_i` — её оценка. Параметр `threshold` задаёт минимальный score теста.

Для **всего набора**:

\[
PassRate = \frac{N_{PASS}}{N_{PASS}+N_{FAIL}}\times 100\%
\]

Пример: 94 успешных из 100 → **94%**, значит при пороге **95%** CI должен завершиться неуспешно.

**Важное правило:** общий pass rate ≥95% не должен маскировать критические ошибки (сломанный API-контракт, утечка секретов, опасный вызов инструмента). Такие сценарии выносят в отдельные обязательные проверки.

## 6. Сравнение baseline и candidate

Пример:

| Версия | PASS | FAIL | Pass rate |
|---|---:|---:|---:|
| Baseline (`abc123`) | 97 | 3 | 97% |
| Candidate (`def456`) | 93 | 7 | 93% |

Падение на **4 процентных пункта**. Но смотреть нужно не только на общий процент: важно выяснить, **какие именно тесты перешли из PASS в FAIL**.

Для честного сравнения желательно сохранять одинаковыми датасет, критерии, параметры модели и условия запуска. Дополнительно фиксировать версию промпта, модель, дату и commit SHA.

## 7. Экспорт отчётов

В статье №3 показан экспорт нескольких форматов:

```bash
npx promptfoo@latest eval -c promptfooconfig.yaml \
  -o results.json \
  -o report.html \
  -o results.junit.xml \
  --tag commit=$GITHUB_SHA
```

- **JSON** — данные для скриптов и расчёта метрик.
- **HTML** — человекочитаемый отчёт.
- **JUnit XML** — формат результатов, понятный многим CI-инструментам.
- **Commit tag** — связь результата с конкретным изменением в Git.

**Важно:** JUnit XML не блокирует merge сам по себе. Блокировка требует неуспешного статуса job и настройки required status checks / rulesets в GitHub.

## 8. CI-gate: от Pull Request до решения о merge

```text
Изменён промпт / датасет / конфигурация
               ↓
        Pull Request
               ↓
     GitHub Actions запускает eval
               ↓
     Assertions → JSON / JUnit / HTML
               ↓
  Проверка pass rate и критических кейсов
               ↓
    PASS → review / возможен merge
    FAIL → красный CI, merge запрещён
           (если статус обязателен)
```

Упрощённый пример workflow из изученной темы:

```yaml
name: LLM eval

on:
  pull_request:
    paths:
      - 'prompts/**'
      - 'evals/**'
      - 'promptfooconfig.yaml'

jobs:
  eval:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: promptfoo/promptfoo-action@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          config: 'promptfooconfig.yaml'
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
```

**Это иллюстрация интеграции, а не готовый workflow, выполняющий весь план.** Для рабочего CI ещё необходимо: настроить экспорт JUnit XML, корректно посчитать порог 95%, обеспечить неуспешный статус job при его нарушении, загрузить отчёты как artifacts и включить обязательную проверку ветки. Актуальные параметры Action следует сверить с его документацией.

Принцип проверки JSON через `jq` и `bc`:

```bash
successes=$(jq '.results.stats.successes' results.json)
failures=$(jq '.results.stats.failures' results.json)

# Сначала убедиться, что оба числа присутствуют и total > 0.
# Иначе завершить job с ошибкой инфраструктуры.
pass_rate=$(echo "scale=2; 100 * $successes / ($successes + $failures)" | bc)

if (( $(echo "$pass_rate < 95" | bc -l) )); then
  echo "Quality gate failed: ${pass_rate}%"
  exit 1
fi
```

**Примечание:** путь полей JSON зависит от версии и должен быть проверен на реальном файле; этот фрагмент не заменяет полный скрипт обработки ошибок.

## 9. Как проверить намеренную регрессию

1. Создать baseline с заведомо рабочим системным промптом и сохранить отчёт.
2. Убедиться, что eval-набор покрывает обычные вопросы, недостаточный контекст, формат ответа и вызовы инструментов.
3. Ухудшить промпт: например, удалить правило «если контекста недостаточно, сообщи об этом».
4. Создать PR с изменением.
5. Проверить, что workflow запустился **автоматически**.
6. Найти конкретные ранее успешные тесты, ставшие FAIL.
7. Проверить отчёты и красный статус обязательной CI-проверки.
8. Убедиться, что merge заблокирован, затем исправить промпт и получить зелёный билд.

Это и есть контрольная точка дня: **silent regression → обнаруженный FAIL → красный CI до production**.

## 10. Гигиена eval-набора

- Хранить промпты, датасеты и assertions в Git; отслеживать версии.
- Ревьюить новые тестовые примеры, проверять ожидаемое поведение.
- Не менять эталонные ответы только ради прохождения новой версии модели.
- Удалять или архивировать устаревшие кейсы с объяснением причины.
- Разделять критические hard checks и допускающие вариативность model-graded проверки.
- Фиксировать версию Promptfoo и модель, учитывать стоимость и лимиты API.
- Не помещать секреты в репозиторий или публичные CI-отчёты.
- Повторять недетерминированные проверки (`--repeat`), при необходимости отключать кэш (`--no-cache`).

## 11. Связь с предыдущей работой

Из eval-набора **дня 37** можно перенести `question`, `context`, `reference_answer` и критерии проверки в тесты Promptfoo. Для проверки **агента с `search_documents`** важно тестировать не только итоговый ответ, но и выбор инструмента, использование найденных документов и соблюдение ограничений. Для тестирования всей системы нужен custom provider, вызывающий RAG/agent pipeline.

## 12. Самопроверка перед практикой

1. Чем регрессионное тестирование отличается от разовой оценки качества?
2. Для чего нужны `prompts`, `providers`, `tests`, `defaultTest`?
3. Почему `llm-rubric` и `contains` могут ошибаться по-разному?
4. Чем weighted score одного теста отличается от pass rate всего набора?
5. Если 76 из 80 тестов прошли, достигнут ли порог 95%?
6. Зачем нужны baseline, commit SHA и JUnit XML?
7. Какие три механизма нужны, чтобы обнаружить FAIL, сделать CI красным и реально запретить merge?
8. Почему проверка фиксированного `context` не обнаружит регрессию retrieval?

## 13. Чек-лист практики дня 40

- [ ] Установить Promptfoo и создать `promptfooconfig.yaml`.
- [ ] Перенести часть eval-набора из дня 37.
- [ ] Локально сравнить два промпта или две модели.
- [ ] Посмотреть таблицу результатов и отдельные FAIL.
- [ ] Добавить GitHub Actions на PR.
- [ ] Сохранять JUnit XML и другие отчёты.
- [ ] Реализовать pass-rate gate ≈95% плюс критические hard checks.
- [ ] Включить required status check для целевой ветки.
- [ ] Вызвать намеренную регрессию и получить красный билд.
- [ ] Исправить промпт и получить зелёный билд.
- [ ] Зафиксировать правила сопровождения eval-набора.

**Итог:** теория трёх источников изучена. До завершения дня остаются итоговая мини-проверка и практическое доказательство того, что CI автоматически обнаруживает намеренную регрессию.

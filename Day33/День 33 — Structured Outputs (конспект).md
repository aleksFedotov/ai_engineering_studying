# День 33 — Structured Outputs: гарантии схемы и ограничения

**Источники:**
1. OpenAI — Structured model outputs: https://developers.openai.com/api/docs/guides/structured-outputs
2. Microsoft Learn — Structured outputs (Azure OpenAI / Microsoft Foundry): https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs

---

## 1. Что такое Structured Outputs

**Structured Outputs (структурированные выходы)** — функция, гарантирующая, что ответ модели **всегда соответствует предоставленной JSON Schema (JSON-схеме)**: модель не может пропустить обязательный ключ или выдумать значение вне перечисления (enum).

**Три преимущества (OpenAI):**
- **Reliable type-safety (надёжная типобезопасность)** — не нужно валидировать ответ и делать ретраи при неверном формате;
- **Explicit refusals (явные отказы)** — отказы по безопасности программно обнаружимы через поле `refusal`;
- **Simpler prompting (упрощённый промптинг)** — не нужно «уговаривать» модель форматировать ответ словами.

**Механика — grammar-constrained decoding (декодирование с ограничением грамматики):**
на каждом шаге генерации вероятности токенов, нарушающих схему, **обнуляются (маскируются)** — модель выбирает только среди «легальных» продолжений. Отсюда 100% валидность **формы**.

> ⚠️ Схема гарантирует форму, но **не истинность содержимого**: на нерелевантном вводе модель может галлюцинировать значения «под схему». Лечение — инструкция в промпте, что возвращать (пустые поля / маркерная фраза), если ввод не под задачу.

**Первый запрос с новой схемой идёт с доп. латентностью** (API компилирует схему), последующие с той же схемой — без задержки (кеш).

---

## 2. JSON mode vs Structured Outputs

| | Structured Outputs | JSON Mode |
|---|---|---|
| Валидный JSON | Да | Да |
| Соответствие схеме | **Да** (поддерживаемое подмножество) | **Нет** |
| Модели | `gpt-4o-mini`, `gpt-4o-2024-08-06` и новее | `gpt-3.5-turbo`, `gpt-4-*`, `gpt-4o-*` и совместимые |
| Включение (Responses API) | `text: { format: { type: "json_schema", "strict": true, "schema": ... } }` | `text: { format: { type: "json_object" } }` |

**Рекомендация:** всегда использовать Structured Outputs, когда возможно.

### ⚠️ Капкан JSON mode (в конспект!)

Без слова **«JSON»** в сообщениях модель может генерировать **бесконечный поток пробелов до исчерпания лимита токенов**. Подстраховка: API кидает ошибку, если строка «JSON» не встречается в контексте. JSON mode гарантирует только синтаксис → нужна валидация библиотекой + ретраи.

---

## 3. Два сценария применения

- **Function calling (вызов функций)** — модель подключается к инструментам системы (БД, UI-действия); схема описывает аргументы функции.
- **`text.format` / `response_format`** — структурируется **ответ модели пользователю** (например, рендер частей ответа в разных блоках UI).

Правило: подключаешь к инструментам/данным → function calling; структурируешь ответ → structured `text.format`.

---

## 4. Кодовые идиомы (Python SDK)

### Responses API (основная)

```python
from openai import OpenAI
from pydantic import BaseModel

client = OpenAI()

class CalendarEvent(BaseModel):
    name: str
    date: str
    participants: list[str]

response = client.responses.parse(
    model="...",
    input=[
        {"role": "system", "content": "Extract the event information."},
        {"role": "user", "content": "Alice and Bob are going to a science fair on Friday."},
    ],
    text_format=CalendarEvent,
)

event = response.output_parsed   # объект CalendarEvent, без json.loads
```

`responses.parse` сам: конвертирует Pydantic → JSON Schema, включает `strict: true`, парсит ответ в **`output_parsed`**.

### Chat Completions (альтернатива, Azure-гайд)

```python
completion = client.beta.chat.completions.parse(
    model="MODEL_DEPLOYMENT_NAME",
    messages=[...],
    response_format=CalendarEvent,
)
event = completion.choices[0].message.parsed   # вместо output_parsed
# message.refusal — проверить ДО обращения к message.parsed
```

### Function calling со strict-инструментами

```python
tools = [openai.pydantic_function_tool(GetDeliveryDate)]  # strict: true автоматически
# Azure: НЕ поддерживается parallel function calls → parallel_tool_calls: false
```

### Streaming

`client.responses.stream(...)` → события `response.output_text.delta`, `response.refusal.delta`, `response.error`, `response.completed`; финал — `stream.get_final_response()`.

---

## 5. Правила strict-схемы (чек-лист)

1. **Корень — всегда объект**, не `anyOf` (ловушка: Zod `discriminatedUnion` даёт `anyOf` на верхнем уровне → невалидно).
2. **Все поля — в `required`**. Опциональность только через union с null: `"type": ["string", "null"]` (поле присутствует, но может быть `null`).
3. **`additionalProperties: false`** — на каждом объекте, всегда.
4. Порядок ключей в выводе = порядку ключей в схеме.
5. Поддерживаются: типы String, Number, Boolean, Integer, Object, Array, Enum, `anyOf`; `$defs`/`$ref`; **рекурсивные схемы** (`"$ref": "#"`).
6. Неподдерживаемая схема при `strict: true` → **ошибка API**, не молчаливое игнорирование.
7. Советы: понятные имена ключей, `description` для важных полей, подбор структуры через evals; схема и типы в коде — из одного источника (SDK-хелперы) или через CI-генерацию, чтобы не разошлись.

---

## 6. Ограничительные ключевые слова: OpenAI vs Azure

| Ключевое слово | OpenAI API | Azure OpenAI |
|---|---|---|
| `pattern`, `format` (строки) | ✅ Поддерживаются (кроме fine-tuned моделей) | ❌ Не поддерживаются |
| `minLength`, `maxLength` | ❌ Не поддерживаются | ❌ Не поддерживаются |
| `minimum`, `maximum`, `multipleOf` | ✅ Поддерживаются (кроме fine-tuned) | ❌ Не поддерживаются |
| `minItems`, `maxItems` | ✅ Поддерживаются (кроме fine-tuned) | ❌ Не поддерживаются |
| Лимит свойств объектов | 5000 | **100** |
| Глубина вложенности | 10 уровней | **5 уровней** |

> **Практическое правило:** проектируй схему по более строгому лимиту (Azure) и **валидируй ограничения значений (длина, паттерн, диапазон) в коде** — тогда схема переносима между платформами.

На Azure также не поддерживаются: `patternProperties`, `unevaluatedProperties`, `propertyNames`, `minProperties`, `maxProperties`, `unevaluatedItems`, `contains`, `minContains`, `maxContains`, `uniqueItems`. У OpenAI не поддерживаются: `allOf`, `not`, `dependentRequired`, `dependentSchemas`, `if`/`then`/`else`.

---

## 7. Три краевых случая (обязательный шаблон обработки)

Даже со strict-схемой валидный структурированный ответ может не сгенерироваться:

| Случай | Признак в ответе | Действие |
|---|---|---|
| **Refusal (отказ модели)** | `content[i].type == "refusal"` (Chat Completions: `message.refusal`) | Показать отказ в UI / условная логика |
| **Обрыв по лимиту токенов** | `status == "incomplete"` + `incomplete_details.reason == "max_output_tokens"` | Ошибка/ретрай с большим лимитом |
| **Контент-фильтр** | `status == "incomplete"` + `incomplete_details.reason == "content_filter"` | Ошибка; JSON может быть частичным |

**Порядок проверок** перед доверием к `output_parsed`:
1. `response.status` / `incomplete_details.reason` → обрыв или фильтр?
2. В `response.output` найти `message` → в `content` есть `type == "refusal"`?
3. Только потом — `output_parsed` / `parsed`.

---

## 8. Azure-специфика (источник №2)

- Endpoint: `https://YOUR-RESOURCE-NAME.openai.azure.com/openai/v1/` — OpenAI-совместимый, используется обычная библиотека `openai`.
- Аутентификация: **Microsoft Entra ID** (`DefaultAzureCredential` + `get_bearer_token_provider`) или API-ключ.
- В `model` передаётся **имя деплоймента** (deployment name), а не имя модели.
- Structured outputs не работают с **parallel function calls** → `parallel_tool_calls: false`.
- Поддержка: с `gpt-4o-2024-08-06` / `gpt-4o-mini-2024-07-18` и новее (gpt-4.1, o-серия, gpt-5.x); первая версия API — `2024-08-01-preview`, GA — `v1`.

---

## 9. Практика по плану дня (что сделать руками)

- [ ] Живой запуск `responses.parse` со своей Pydantic-моделью → типизированный объект в `output_parsed` без `json.loads`.
- [ ] Написать обработчик трёх краевых случаев (refusal / `max_output_tokens` / `content_filter`) по шаблону из раздела 7.
- [ ] Проверить ограничения на практике: `minLength`/`maxLength` — только валидацией в коде; на Azure — также `pattern`, `format`, `min`/`max`, `minItems`/`maxItems`.
- [ ] Убедиться: модель возвращает ответ строго по Pydantic-модели со 100% валидностью формы (контрольная точка дня ✅).

---

## 10. Однострочные выводы

1. JSON mode гарантирует синтаксис, Structured Outputs — соответствие схеме.
2. 100% валидность формы достигается маскированием «нелегальных» токенов при генерации — но не гарантирует истинность содержимого.
3. Strict-схема: все поля в `required`, `additionalProperties: false`, опциональность — через `["string", "null"]`, корень — объект.
4. Refusal, обрыв по токенам и контент-фильтр проверяются кодом **до** чтения распарсенного результата.
5. Ограничения значений (длина, паттерн, диапазон) на Azure не принуждаются схемой — валидировать в коде; проектировать схемы по более строгой платформе.

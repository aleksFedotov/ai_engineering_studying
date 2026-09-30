# День 34 — Instructor: валидация и авторетраи; когда что выбирать

> Конспект по трём источникам:
> 1. DeepLearning.AI: «Pydantic for LLM Workflows» (курс, 1 ч 50 мин, 8 уроков)
> 2. Документация Instructor — python.useinstructor.com
> 3. Machine Learning Mastery: «Structured Outputs vs. Function Calling: Which Should Your Agent Use?»

---

## 0. Главная формула дня (контрольная точка)

- **Structured output (структурированный вывод)** — про **форму данных** (shape of the data): экстракция, парсинг, строгие ответы.
- **Function calling (вызов функций)** — про **поток управления** (control flow): нужны внешние данные или действие посреди рассуждения.

Критерий выбора для новой задачи: «Вся нужная информация уже в контексте? → structured output. Нужен внешний мир или условное действие в середине мысли? → function calling».

---

## 1. Pydantic как контракт (источник №1)

**Проблема:** LLM возвращает свободный текст (free-form text) — его невозможно надёжно передать следующему компоненту системы. Pydantic-модель = контракт на границе компонентов: невалидные данные физически не проходят дальше.

### Базовая модель входа

```python
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Literal
from datetime import date

class UserInput(BaseModel):
    name: str
    email: EmailStr                 # валидный email (нужен пакет email-validator)
    query: str
    order_id: Optional[int] = Field(None, ge=10000, le=99999,
                                    description="5-значный номер заказа")
    purchase_date: Optional[date] = None
```

- Объявление типов (type hints) = валидация.
- `Field(...)` — обязательное поле; `Field(None, ...)` — опциональное.
- `description` попадает в схему, которую видит LLM, — это часть промпта.
- Проверка JSON: `UserInput.model_validate_json(raw)` → бросает `ValidationError` с точным описанием проблемы.

### Модель ответа LLM через наследование

```python
class CustomerQuery(UserInput):
    priority: str = Field(..., description="low / medium / high")
    category: Literal['refund_request', 'information_request', 'other']
    is_complaint: bool
    tags: List[str]
```

`Literal[...]` — перечисление допустимых значений; выдуманная категория будет отсечена валидатором.

### Три метода получить структуру от LLM (эскалация надёжности)

1. **Попросить JSON в промпте** — хрупко (лишний текст, битый JSON).
2. **Схема в промпт + валидация ответа**: `CustomerQuery.model_json_schema()` → вставить в промпт → ответ проверить через `model_validate_json`.
3. **Instructor**: `response_model=CustomerQuery` — библиотека сама подставляет схему, парсит, валидирует, переспрашивает при ошибке.

### Tool calling на Pydantic

```python
class CheckOrderStatusArgs(BaseModel):
    order_id: str = Field(..., description="Формат: ABC-12345")

    @field_validator("order_id")
    def validate_order_id(cls, v):
        import re
        if not re.match(r"^[A-Z]{3}-\d{5}$", v):
            raise ValueError("order_id должен быть в формате ABC-12345")
        return v
```

- `@field_validator` — кастомный валидатор: произвольная логика поверх типов.
- В агентных фреймворках ошибка валидации аргументов возвращается модели → она повторяет вызов с исправлением (та же петля «ошибка → переспрос»).
- Сквозной паттерн курса: валидированный ввод → анализ LLM → вызов инструмента с валидированными аргументами → структурированный финальный ответ (тикет).

---

## 2. Instructor: механика и настройка (источник №2)

Библиотека поверх Pydantic: типобезопасная экстракция, валидация, авторетраи, стриминг; 15+ провайдеров через единый вход:

```python
import instructor
client = instructor.from_provider("openai/gpt-4.1-mini")
# тот же интерфейс: "anthropic/...", "google/...", "ollama/llama3.2"

person = client.create(
    response_model=Person,
    messages=[{"role": "user", "content": "..."}],
    max_retries=3,
)
```

Позиционирование от самой команды: **Instructor — экстракция, PydanticAI — агенты**.

### Механика ретрая (reasking)

При `ValidationError` в тот же диалог добавляются:

```python
kwargs["messages"].append(response.choices[0].message)   # невалидный ответ модели
kwargs["messages"].append({
    "role": "user",
    "content": f"Please correct the function call; errors encountered:\n{e}",
})
```

Модель видит свой невалидный ответ + конкретный текст ошибки. Защита от двух классов сбоев: ошибки валидации Pydantic и ошибки декодирования JSON. Сообщение об ошибке валидации = промпт для следующей попытки.

### Два разных max_retries — не путать!

| Параметр | Что настраивает |
|---|---|
| `OpenAI(max_retries=2)` | Транспортные повторы SDK (HTTP-ошибки, 429, таймауты) |
| `client.create(max_retries=2, ...)` | Повторы валидации Instructor: 1 первая попытка + до 2 ретраев = максимум 3 вызова |

**Нельзя перемножать лимиты** — произведение лишь верхняя граница; реальное число запросов зависит от того, где именно возникли сбои. Всегда передавайте `max_retries` явно (дефолты в разных местах API разные: 0 и 1).

### Два вида валидации

**Код-валидация** (детерминированная, бесплатная):

```python
from pydantic import AfterValidator
from typing import Annotated

def name_must_contain_space(v: str) -> str:
    if " " not in v:
        raise ValueError("Name must contain a space.")
    return v.lower()

class UserDetail(BaseModel):
    age: int
    name: Annotated[str, AfterValidator(name_must_contain_space)]
```

**LLM-валидация** (правило проверяет другая модель; текст ошибки генерирует LLM — удобно для переспрашивания, но дорого и недетерминированно):

```python
from instructor import llm_validator

answer: Annotated[str, BeforeValidator(
    llm_validator("don't say objectionable things", client=client))]
```

Правило: всё, что выразимо кодом («дата не в прошлом», формат ID), валидируйте кодом.

### Контекст валидации — анти-галлюцинаторный барьер

```python
class QuoteExtraction(BaseModel):
    claim: str
    supporting_quote: str

    @field_validator('supporting_quote')
    @classmethod
    def verify_quote(cls, v: str, info: ValidationInfo):
        ctx = info.context
        if ctx and v.strip() not in ctx.get('source_text', ''):
            raise ValueError("Цитата должна быть точной подстрокой источника.")
        return v

client.create(..., context={"source_text": source_text}, max_retries=2)
```

Принцип: **генерация вероятностная, проверка детерминированная**.

### Режимы (Modes) — как Instructor достаёт JSON из разных моделей

| Режим | Суть | Когда |
|---|---|---|
| `TOOLS` | Через tool calling API | По умолчанию для большинства |
| `JSON_SCHEMA` | Нативное принуждение к схеме (strict structured outputs) | Если провайдер умеет |
| `MD_JSON` | JSON в markdown-блоке | Слабые/локальные модели без tools |
| `PARALLEL_TOOLS` | Несколько вызовов инструментов за ответ | Параллельные задачи |

Instructor = диспетчер: берёт `model_json_schema()` из вашей модели и выбирает транспорт под провайдера. Модель-контракт не меняется. Важно: в режиме `TOOLS` экстракция физически едет через machinery function calling (см. раздел 3.5).

### Расход и наблюдаемость

- Ретрай = полный повторный запрос с **растущим контекстом** (невалидные ответы копятся) → ретрай №3 дороже №1.
- `token_budget=2000` → остановка ретраев по совокупным токенам, исключение `TokenBudgetExceeded`. Проверка — *после* неудачной валидации, *до* следующего запроса; успешный ответ вернётся, даже если сумма превысила бюджет.
- Исчерпание попыток → `InstructorRetryException` с `e.n_attempts` и `e.failed_attempts`.
- Хуки: `client.on("completion:kwargs", ...)`, `client.on("completion:error", ...)` — для логирования.
- `create_with_completion()` → (объект, сырой ответ API) — видеть расход токенов.
- Тонкая настройка: `max_retries=Retrying(...)` из Tenacity (повтор по типу ошибки, экспоненциальная пауза, условие остановки). **Всегда задавать stop-условие** — иначе бесконечный цикл.
- Рекомендации по попыткам: rate limits — 5; ошибки валидации — 2–3; сеть — 4.
- Мелочь: `disable_pydantic_error_url()` экономит токены в сообщениях об ошибках.

---

## 3. Архитектурный выбор (источник №3)

### 3.1. Механика под капотом

**Structured outputs** = декодирование с грамматическими ограничениями (grammar-constrained decoding): на каждом шаге генерации вероятности токенов, нарушающих схему, обнуляются. Ошибка формы становится *невозможной в принципе* → ~100% соответствие схеме, один вызов.

> Контраст: Instructor-ретраи = «проверить после и исправить» (коррекция, снаружи модели); constrained decoding = «не дать ошибиться» (предотвращение, внутри генерации).

**Function calling** = instruction tuning: модель натренирована распознавать «не хватает данных» / «нужно действие». Цикл:

1. Модель выдаёт имя инструмента + аргументы.
2. **Модель приостанавливается — сама код не исполняет.**
3. Ваш код исполняет функцию локально.
4. Результат возвращается модели.
5. Модель синтезирует финальный ответ.

### 3.2. Когда structured outputs

Критерий: вся информация уже в промпте/контексте, нужно только переформатировать.

- **ETL / экстракция**: сырой текст → строгая схема БД (транскрипт → имена, даты, тональность).
- **Генерация запросов**: естественный язык → валидный SQL/GraphQL (сломанная схема = сломанный запрос).
- **Структурированное рассуждение**: обязательные поля `thought_process` → `assumptions` → `decision` (принудительный Chain-of-Thought; порядок полей в модели = порядок генерации: сначала «почему», потом «что»).

### 3.3. Когда function calling

Критерий: внешние данные/действия, динамические решения посреди рассуждения.

- **Реальные действия**: `book_flight(destination="JFK")`.
- **Агентный RAG**: модель сама решает, *какие* термины искать и нужен ли поиск вообще (`search_knowledge_base`).
- **Маршрутизация**: выбор субагента (`delegate_to_billing_agent` vs `delegate_to_tech_support`).

### 3.4. Экономика

| Измерение | Structured outputs | Function calling |
|---|---|---|
| Токены | Один вызов | Несколько round-trip'ов; контекст растёт на каждом |
| Задержка | Минимальная | Ждём модель → исполняем код → снова ждём |
| Надёжность | ~100% формы (constrained decoding) | Статистически непредсказуем: выдуманные аргументы, не тот инструмент, циклы → нужны ретраи и фолбэки |

Практические выводы:
- Два типа сбоев FC: **неправильный выбор инструмента** (не лечится валидатором аргументов) и **невалидные аргументы** (лечится Pydantic-валидатором).
- Каждая tool definition стоит токенов в *каждом* запросе — держите набор инструментов малым.
- «Один вызов» у structured output — при условии, что валидация прошла с первого раза (llm_validator и кастомные валидаторы могут запустить ретраи).

### 3.5. Гибридные паттерны

- Современный function calling сам опирается на structured outputs (аргументы должны совпадать с сигнатурой).
- «Фейковый» tool use: модель возвращает JSON с описанием действия, детерминированный код исполняет его *после* генерации — без многошаговой задержки.
- **Controller (контроллер)**: агент-«мозг» на function calling — собирает контекст вызовами инструментов.
- **Formatter (форматировщик)**: сырые результаты → финальный дешёвый вызов только со structured outputs → идеальное совпадение с UI/REST API.

### 3.6. Дерево решений (выучить)

1. Нужны внешние данные посреди мысли или действие? → **Function calling**
2. Просто парсинг/экстракция/перевод неструктурированного контекста в структуру? → **Structured outputs**
3. Нужна абсолютная строгость сложного вложенного объекта? → **Structured outputs через constrained decoding**

Финальная мысль статьи: function calling — мощная, но непредсказуемая способность, применять экономно и с обработкой ошибок; structured outputs — надёжный «клей» AI-пайплайнов.

---

## 4. Важные примирения и оговорки

- **«Два уровня описания»**: на уровне API-транспорта всё — JSON-схемы и tool calls (Instructor в режиме `TOOLS` делает экстракцию через machinery function calling). На уровне архитектурного намерения — форма (нет цикла исполнения) vs действие (цикл «модель → код → модель»). Критерий выбора — про намерение.
- **Constrained decoding гарантирует форму, а не истинность**: `order_id` будет валидной строкой, но может быть выдуманным → смысловые валидаторы нужны и в strict-режиме.
- **Ограничения strict structured outputs (OpenAI)**: не весь JSON Schema поддерживается (требуется `additionalProperties: false`, все поля в `required`, ограниченная глубина вложенности). Экзотичная модель → отказ провайдера → запасной путь: режим `TOOLS` + ретраи.
- **Актуализация API**: вместо `instructor.patch(OpenAI())` — `instructor.from_openai(client, mode=...)` / `from_provider("provider/model")`. Для OpenAI — `client.responses.parse(...)` (Responses API), не `beta.chat.completions.parse`.
- Синтаксис везде Pydantic **v2** (`field_validator`, `model_validate_json`); `@validator`, `parse_raw`, `min_items` — это устаревшая v1 (в v2: `min_length`).

---

## 5. Чек-лист практики дня

- [ ] `pip install instructor` (+ `email-validator`)
- [ ] Описать ответ как `BaseModel`, вызвать через `from_provider`, `response_model=...`
- [ ] Спровоцировать невалидный ответ → увидеть авторетрай с текстом ошибки валидации (`max_retries=3`)
- [ ] Кастомный валидатор «дата не в прошлом» → убедиться, что ретрай его учитывает
- [ ] Выписать дерево решений и таблицу экономики в конспект (разделы 3.4 и 3.6 — уже выписаны)
- [ ] Контрольная точка: уметь обосновать выбор механизма одной фразой (форма vs поток управления)

---

## 6. Мини-словарь терминов

| Русский термин | English |
|---|---|
| Структурированный вывод | structured output |
| Вызов функций / инструментов | function calling / tool use |
| Валидация данных | data validation |
| Кастомный валидатор | custom validator (`field_validator`) |
| Автоповтор / переспрашивание | retry / reasking |
| Декодирование с грамматическими ограничениями | grammar-constrained decoding |
| Поток управления | control flow |
| Форма данных | shape of the data |
| JSON-схема модели | `model_json_schema()` |
| Проверка JSON по модели | `model_validate_json()` |
| Контекст валидации | validation context (`context=`, `ValidationInfo`) |
| Исключение исчерпания ретраев | `InstructorRetryException` |
| Бюджет токенов на ретраи | `token_budget` |
| Задержка | latency |
| Цепочка рассуждений | Chain-of-Thought |
| Генерация с поиском | retrieval-augmented generation (RAG) |

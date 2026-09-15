# День 23 — Chroma: первая векторная БД

> Конспект по двум источникам: Chroma Getting Started (docs.trychroma.com) и Chroma Filters (cookbook.chromadb.dev). Термины: русский + английский оригинал.

---

## 1. Базовые понятия

**Векторная база данных (vector database)** — БД, хранящая эмбеддинги (embeddings) вместе с документами и метаданными, с быстрым поиском ближайших соседей.

**Коллекция (collection)** — аналог таблицы: хранит три типа данных:
- `documents` — тексты чанков;
- `embeddings` — векторы;
- `metadatas` — структурированные поля (source, page, chunk_index…).

**ID** — обязательное поле при `add`, уникальная строка.

Под капотом — приближённый поиск ближайших соседей (approximate nearest neighbors, ANN), индекс HNSW.

## 2. Клиенты Chroma

| Клиент | Команда | Поведение |
|---|---|---|
| In-memory | `chromadb.Client()` | данные теряются при завершении программы |
| Persistent | `chromadb.PersistentClient(path="./chroma_db")` | пишет на диск, переживает перезапуск |
| Клиент-сервер | `chromadb.HttpClient()` + `chroma run` | для прода / нескольких пользователей |

⚠️ Гайд Getting Started по умолчанию показывает in-memory — для реального проекта брать `PersistentClient` с явным `path`.

## 3. Основные операции

```python
import chromadb
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="docs")  # не падает при повторном запуске

collection.add(          # add — падает на дублях ID; upsert — перезаписывает
    ids=["doc_0", "doc_1"],
    documents=["текст чанка 0", "текст чанка 1"],
    embeddings=[[...], [...]],                  # свои векторы (день 21)
    metadatas=[{"source": "a.pdf", "page": 3}, {"source": "b.pdf", "page": 1}],
)

results = collection.query(
    query_embeddings=[query_vec],   # СВОЙ вектор, не query_texts!
    n_results=5,                    # по умолчанию 10
)
```

**Если не передать `embeddings=`** — Chroma эмбеддит сама дефолтной моделью (all-MiniLM-L6-v2, ONNX, качается при первом запуске).

### Главное правило
Свои эмбеддинги в `add` ⇒ эмбеддим запрос **той же моделью** и используем `query_embeddings`.
`query_texts` + чужие векторы = запрос попадает в другое векторное пространство (embedding space), distances бессмысленны.

Для E5-моделей (напр. `intfloat/multilingual-e5-small`) — префиксы: документы `"passage: "`, запросы `"query: "` (как в дне 21).

## 4. Структура результата

```python
{
  'ids':       [['id1', 'id2', ...]],   # двойная вложенность!
  'documents': [[...]],                 # внешний список = запросы (batch),
  'distances': [[0.15, 0.42, ...]],     # внутренний = топ-N на запрос
  'metadatas': [[{...}, {...}]],
}
```

**distances — расстояния, не сходства: меньше = ближе = релевантнее.**

- Дефолт: L2 (евклидово расстояние).
- Косинусное пространство: `create_collection(..., metadata={"hnsw:space": "cosine"})`.
- Перевод: `cosine_similarity = 1 − distance` (только для cosine-пространства!).
- Большое distance в хвосте топ-N → чанк нерелевантен, резать по порогу.

## 5. Фильтры

Два типа, комбинируются (работают как И), доступны в `query()` и `get()`:

| | `where` | `where_document` |
|---|---|---|
| По чему | метаданные (поля, которые сами положили) | текст документа |
| Операторы | `$eq $ne $gt $gte $lt $lte $in $nin` `$contains $not_contains` (массивы) | `$contains $not_contains $regex $not_regex` |

⚠️ **`$contains` двойственен**: в `where` — вхождение элемента в массив (Chroma ≥ 1.5.0); в `where_document` — подстрока в тексте.

### Операторы по метаданным (`where`)

- Типы значений: str, bool, int, float. Сравнение строк **регистрозависимо**.
- `$gt/$gte/$lt/$lte` — **только числа** (`{"page": {"$gt": "5"}}` → ValueError).
- `$in` / `$nin` — список значений **одного типа** (`[1, "2", 1.1]` упадёт). `$nin` также матчит записи без этого поля.
- Короткая форма `{"source": "a.pdf"}` = `$eq`, но только **одно** условие.
- На верхнем уровне — либо одно условие, либо один логический оператор. `{"source": ..., "page": ...}` рядом — невалидно, нужен `$and`.

### Логические операторы

```python
where={
    "$and": [                                    # минимум 2 условия!
        {"$or": [{"source": "отчёт.pdf"}, {"source": "презентация.pdf"}]},
        {"page": {"$gte": 3}},
        {"page": {"$lte": 20}},
    ]
}
```
Вложенность разрешена. Эквивалент `$or` по одному полю: `{"source": {"$in": ["a.pdf", "b.pdf"]}}`.

### Фильтры по документу (`where_document`)

```python
where_document={"$and": [{"$contains": "продажи"}, {"$not_contains": "черновик"}]}
```
`$contains` — регистрозависимый поиск подстроки ("Hello" ≠ "hello"). Полей внутри нет.

### `get()` — отладка

```python
collection.get(where={"source": "файл.pdf"}, limit=10, offset=0)
```
Выборка без векторного поиска + пагинация. Использовать для проверки «что реально проходит фильтр» перед отладкой query.

## 6. Как работает фильтрация

**Пред-фильтрация (pre-filtering)**: сначала отбирается подмножество записей по фильтру, топ-N ищется только внутри него. Если проходит мало записей — вернётся меньше, чем `n_results` (это норма, не баг).

## 7. Типичные грабли (чек-лист)

1. `chromadb.Client()` вместо `PersistentClient` → данные потеряны.
2. `query_texts` при своих эмбеддингах → бессмысленные distances.
3. numpy-массив в `query_embeddings` → `.tolist()`.
4. Дубли ID при повторном запуске → `upsert` или чистая папка базы.
5. Модель создаётся внутри функции поиска → выносить на уровень модуля.
6. E5 без префиксов `query:`/`passage:` → завышенные distances.
7. Регистр/путь в `source` не совпал с фильтром → отладка через `get(where=...)`.
8. Примеры из доков (cookbook) используют `query_texts` — не копировать дословно в проект со своими векторами.

## 8. Контрольная точка дня

✅ Семантический поиск по своим документам за ~15 строк кода; фильтр по источнику реально сужает выдачу.

Минимальный рабочий скрипт:

```python
import json, chromadb
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("intfloat/multilingual-e5-small")
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="docs")

chunks = [json.loads(l) for l in open("Day21/OUTPUT/index.jsonl", encoding="utf-8")]
collection.add(
    ids=[str(c["id"]) for c in chunks],
    documents=[c["text"] for c in chunks],
    embeddings=[c["vector"] for c in chunks],
    metadatas=[{"source": c.get("source", ""), "page": c.get("page", 0)} for c in chunks],
)

vec = model.encode("query: " + "тестовая фраза").tolist()
res = collection.query(query_embeddings=[vec], n_results=5,
                       where={"source": "файл.pdf"})
for d, dist in zip(res["documents"][0], res["distances"][0]):
    print(f"{dist:.3f} | {d[:80]}")
```

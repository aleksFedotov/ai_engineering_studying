# День 24 — Qdrant: метаданные, фильтрация, обновление индекса

Конспект по источникам дня + разбор вопросов самопроверки.

---

## Источник №1: Qdrant Local Quickstart (официальная документация)

### Структура источника
1. Download and run — запуск через Docker, порты, хранилище
2. Initialize the client — подключение Python-клиента
3. Create a collection — коллекция с размерностью и метрикой
4. Add vectors — upsert точек (vector + payload)
5. Run a query — базовый поиск ближайших векторов
6. Add a filter — поиск с фильтром по payload
7. Next steps — туториалы, облако, production checklist

### Ключевые идеи

**Запуск сервера:**
```bash
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v "$(pwd)/qdrant_storage:/qdrant/storage:z" \
  qdrant/qdrant
```
- REST API: `localhost:6333`, дашборд: `localhost:6333/dashboard`, gRPC: `6334`
- Монтирование тома (`-v`) — данные переживают перезапуск контейнера

**Клиент:**
```python
from qdrant_client import QdrantClient
client = QdrantClient(url="http://localhost:6333")
```

**Коллекция (collection)** — именованный набор точек с векторами одной размерности и одной метрикой:
```python
from qdrant_client.models import Distance, VectorParams
client.create_collection(
    collection_name="test_collection",
    vectors_config=VectorParams(size=4, distance=Distance.DOT),  # в quickstart DOT!
)
```
> В плане дня требуется **cosine**: `Distance.COSINE`. DOT ≡ cosine только на нормализованных векторах (‖v‖ = 1).

**Точка (point) = id + vector + payload**
- Payload — произвольные JSON-метаданные (например `{"source": "report.pdf", "page": 12}`)
- **Upsert** — «вставить или перезаписать» по совпадению id; отдельной операции insert в API нет
- `wait=True` — дождаться реальной записи (иначе операция асинхронная)

**Поиск:**
```python
client.query_points(
    collection_name="test_collection",
    query=[0.2, 0.1, 0.9, 0.7],
    limit=3,
    with_payload=True,   # по умолчанию payload и vector в ответ не входят
)
```
- Результаты — в порядке убывания сходства, поле `score`
- Под капотом — приближённый поиск ближайших соседей (ANN) на индексе HNSW

**Фильтр (pre-filtering — фильтр применяется во время обхода индекса):**
```python
from qdrant_client.models import Filter, FieldCondition, MatchValue
client.query_points(
    collection_name="test_collection",
    query=[0.2, 0.1, 0.9, 0.7],
    query_filter=Filter(
        must=[FieldCondition(key="city", match=MatchValue(value="London"))]
    ),
    limit=3,
)
```
- Post-filtering (найти top-k, потом отфильтровать) — опасен: можно получить меньше результатов, чем limit, и худшего качества

---

## Источник №2: Qdrant Essentials Course, день 3 — Hybrid Search Demo

### Структура источника
1. The Hybrid Search Challenge — постановка проблемы
2. Environment Setup — `qdrant-client[fastembed]`
3. Collection with Named Vectors — dense + sparse
4. Upload Cheese Dataset — 10 документов, автогенерация эмбеддингов
5. Dense vs Sparse — сравнение поведения
6. RRF — Reciprocal Rank Fusion
7. DBSF — Distribution-Based Score Fusion
8. Evaluation — почему «на глазок» качество не оценить

### Ключевые идеи

**Проблема гибридного поиска:**
- Разные шкалы score: dense — cosine в [-1, 1], sparse — BM25 без ограничений
- Разные наборы результатов на один запрос
- Чувствительность к словарю: sparse вернёт 0, если слов запроса нет в документах (vocabulary mismatch)
- Dense всегда вернёт limit результатов (косинус существует между любыми векторами)

**Именованные вектора (named vectors)** — несколько векторов у одной точки:
```python
client.create_collection(
    collection_name="hybrid_search_demo",
    vectors_config={
        "dense": models.VectorParams(distance=models.Distance.COSINE, size=384),
    },
    sparse_vectors_config={
        "sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)
    },
)
```
- Dense — семантика (смысл); sparse — точные совпадения слов (BM25)
- При поиске вектор выбирается через `using="dense"` / `using="sparse"`

**FastEmbed (`models.Document`)** — клиент сам вычисляет эмбеддинг локально:
```python
vector={
    "dense": models.Document(text=doc, model="sentence-transformers/all-MiniLM-L6-v2"),
    "sparse": models.Document(text=doc, model="Qdrant/bm25"),
}
```

**Точка без одного из векторов:**
- видна в поиске по имеющемуся вектору
- невидима в поиске по отсутствующему
- в гибриде получает баллы только от имеющейся составляющей

**RRF (Reciprocal Rank Fusion)** — использует только ранги, не score:
```
RRF_score(d) = Σ  1 / (k + rank_i(d)),   k = 2 в Qdrant
```
```python
prefetch=[
    models.Prefetch(query=..., using="sparse", limit=3),
    models.Prefetch(query=..., using="dense", limit=3),
],
query=models.FusionQuery(fusion=models.Fusion.RRF),
limit=3,
```
- Prefetch — независимый top-k от каждого метода; всё в одном API-вызове
- Если sparse вернул 0 — гибрид вырождается в чистый dense (штатно, не ошибка)

**DBSF** — нормализует score каждого метода (по распределению) и суммирует. На малом датасете дал те же ранжирования, что RRF — но это не общее правило.

**Рекомендации продакшна:** начинать с RRF; prefetch limit делать больше финального limit (иначе fusion не из чего собирать); для оценки качества нужен ground truth + метрики (precision, recall, NDCG), A/B-тесты; дальше — реранкеры (cross-encoders).

---

## Разъяснения тьютора (важные дополнения)

1. **Почему cosine для текстов:** измеряет угол, игнорирует длину вектора. Семантика — в направлении, а не в норме. Евклидово расстояние и DOT зависят от длины.
2. **Сценарий «документ обновился»:**
   - Классика: `delete` по фильтру (`source == "guide.pdf"`) → чанкинг → эмбеддинги → `upsert`
   - Одним upsert можно обойтись только при стабильных ID и неизменном числе чанков; если новая версия короче — старые «лишние» чанки останутся мусором
   - Продакшн-порядок: upsert новых **до** удаления старых (окно с дублями лучше окна с пропавшим документом)
   - В гибридном индексе обновлять **оба** вектора (dense и sparse), иначе получатся «половинчатые» точки
3. **Эксплуатация:** `set_payload` — обновить метаданные без пересчёта эмбеддингов; `delete` принимает фильтр (FilterSelector)
4. **RRF vs DBSF:** RRF отбрасывает величину score (стабильность), DBSF её сохраняет через нормализацию (чувствительность к «уверенности» метода)
5. **Замечание:** Quickstart демонстрирует Qdrant Cloud / DOT-метрику — для плана дня используем локальный Docker и cosine. Код переносим, отличается строка подключения.

---

## Итоги самопроверки

- Источник №1: 7/7 (уточнения: `with_vectors` во мн. числе; insert-семантики нет, upsert — единственная операция записи)
- Источник №2: 6.5/7 (недожат ответ про prefetch=0 от sparse: ничего не ломается, гибрид вырождается в dense — это желаемое поведение)
- Итоговая проверка: 6.5/7 (слабое место — аргументация «почему cosine»: угол, а не длина вектора)

## Контрольная точка дня
Умею не только «залить и искать», но и точечно обновлять индекс: upsert по ID, set_payload, delete по фильтру, сценарий «документ обновился» с изменением числа чанков.

## Практика (план дня)
1. Поднять Qdrant в Docker (с томом для персистентности)
2. Коллекция с явной размерностью + cosine, загрузка индекса через qdrant-client
3. Поиск с фильтром по payload (источник, страница); проверить pre-filtering руками
4. Upsert по существующему ID, set_payload, удаление по фильтру
5. Смоделировать «документ обновился»: переиндексировать только его чанки

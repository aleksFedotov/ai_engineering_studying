import json
import chromadb
from sentence_transformers import SentenceTransformer

# 1. Модель — та же, что в дне 21, загружаем ОДИН раз
model = SentenceTransformer("intfloat/multilingual-e5-small")

# 2. Persistent-клиент с явным путём
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="docs")

# 3. Загрузка index.jsonl
chunks = [json.loads(l) for l in open("Day21/OUTPUT/index.jsonl", encoding="utf-8")]
collection.add(
    ids=[str(c["id"]) for c in chunks],
    documents=[c["text"] for c in chunks],
    embeddings=[c["vector"] for c in chunks],
    metadatas=[{"source": c.get("source", ""),
                "page": c.get("page", 0),
                "chunk_index": c.get("chunk_index", 0)} for c in chunks],
)
print(f"Загружено чанков: {collection.count()}")

# 4. Запрос БЕЗ фильтра
q = "ваша тестовая фраза"
vec = model.encode("query: " + q).tolist()   # префикс — если так было в дне 21!
res_all = collection.query(query_embeddings=[vec], n_results=5)
print("\n=== Без фильтра ===")
for doc, dist, meta in zip(res_all["documents"][0],
                           res_all["distances"][0],
                           res_all["metadatas"][0]):
    print(f"{dist:.3f} | {meta['source']} | {doc[:80]}...")

# 5. Тот же запрос С фильтром по источнику
res_filtered = collection.query(
    query_embeddings=[vec],
    n_results=5,
    where={"source": "файл.pdf"},   # подставьте реальное имя из метаданных
)
print("\n=== С фильтром ===")
for doc, dist in zip(res_filtered["documents"][0], res_filtered["distances"][0]):
    print(f"{dist:.3f} | {doc[:80]}...")

# 6. Бонус: комбинация $and/$or
res_combo = collection.query(
    query_embeddings=[vec],
    n_results=5,
    where={"$and": [
        {"$or": [{"source": "файл.pdf"}, {"source": "другой.pdf"}]},
        {"page": {"$gte": 3}},
    ]},
)
print(f"\n=== $and/$or === найдено: {len(res_combo['ids'][0])}")
import json
from pathlib import Path
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from qdrant_client.models import Prefetch, FusionQuery, Fusion,SparseVector
from fastembed import SparseTextEmbedding; 
from sentence_transformers import CrossEncoder
import re

from tqdm import tqdm

model = SentenceTransformer("intfloat/e5-base-v2")
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")  # ~90 МБ
client = QdrantClient(url="http://localhost:6333")
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


CONFIGS = [
    ("chunks_512",         "dense"),
    ("chunks_512_hybrid",  "hybrid"),
    ("chunks_512_hybrid",  "hybrid_rerank"),
    ("chunks_256",         "dense"),
    ("chunks_256_hybrid",  "hybrid"),
    ("chunks_256_hybrid",  "hybrid_rerank"),
]

def print_summary(rows):
    print("\n" + "=" * 62)
    print(" СВОДНАЯ ТАБЛИЦА")
    print("=" * 62)
    print(f"{'Коллекция':<22}{'Тип':<15}{'k':>3}{'R@k':>8}{'MRR':>8}{'hits':>10}")
    print("-" * 66)
    for r in rows:
        print(f"{r['collection']:<22}{r['type']:<15}{r['k']:>3}"
              f"{r['hit_rate']:>7.1%}{r['mrr']:>8.4f}"
              f"{r['hits']:>6}/{r['total']}")
    print("-" * 62)
    # группировка по k для читаемости
    for k in (1, 5):
        best = max((r for r in rows if r['k'] == k), key=lambda r: r['mrr'])
        print(f"  лучший MRR@{k}: {best['collection']} / {best['type']} ({best['mrr']:.4f})")

def dense_search(query:str, collection_name: str, limit: int = 5):
        q_vec = model.encode(["query: " + query], normalize_embeddings=True)[0].tolist()
        return client.query_points(
                collection_name=collection_name,
                query=q_vec,
                limit=limit
            ).points

def hybrid_search(query: str, collection: str, limit: int = 5):
    dense_q = model.encode(["query: " + query], normalize_embeddings=True)[0].tolist()
    sparse_q = list(sparse_model.embed([query]))[0]

    return client.query_points(
        collection_name=collection,
        prefetch=[
            Prefetch(query=dense_q, using="dense", limit=20),
            Prefetch(query=SparseVector(indices=sparse_q.indices.tolist(),
                                        values=sparse_q.values.tolist()),
                     using="sparse", limit=20),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=limit,
    ).points

def hybrid_search_reranked(query: str, collection: str, k_final: int = 5, k_candidates: int = 20):

    candidates = hybrid_search(query, collection, limit=k_candidates)


    pairs = [(query, c.payload["text"]) for c in candidates]
    scores = reranker.predict(pairs)

    # 3. пересортировка по скору реранкера
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return [c for c, _ in ranked[:k_final]]

def evaluate_retrieval(collection_name, golden_set, type, top_k):
    if type not in ("dense", "hybrid", "hybrid_rerank"):
        raise ValueError(f"Неизвестный type: {type!r}. "
                         f"Ожидается 'dense', 'hybrid' или 'hybrid_rerank'")

    size_suffix = re.search(r"\d+", collection_name).group(0)
    expected_key = f"expected_ids_{size_suffix}"

    hits = 0
    rr_sum = 0.0
    valid = 0
    misses = []

    for q in tqdm(golden_set, desc=f"{collection_name}/{type}/k={top_k}"):
        if q.get("is_negative"):
            continue
        expected_ids = q.get(expected_key)
        if not expected_ids:
            continue
        valid += 1

        if type == "dense":
            points = dense_search(q["question"], collection_name, limit=top_k)
        elif type == "hybrid":
            points = hybrid_search(q["question"], collection_name, limit=top_k)
        else:  # hybrid_rerank
            points = hybrid_search_reranked(q["question"], collection_name,
                                            k_final=top_k, k_candidates=20)

        retrieved_ids = [p.payload["chunk_id"] for p in points]

        hit_rank = None
        for rank, rid in enumerate(retrieved_ids, start=1):
            if rid in expected_ids:
                hit_rank = rank
                break

        if hit_rank is not None:
            hits += 1
            rr_sum += 1.0 / hit_rank
        else:
            misses.append({
                "question_id": q["id"],
                "question": q["question"],
                "expected_ids": expected_ids,
                "retrieved": [
                    {"id": p.payload["chunk_id"],
                     "score": round(p.score, 4),
                     "snippet": p.payload["text"][:150]}
                    for p in points[:5]
                ],
            })

    # защита от деления на ноль: если валидных вопросов нет — это тоже ошибка, а не None
    if valid == 0:
        raise ValueError(f"{collection_name}: ни одного валидного вопроса "
                         f"(проверь {expected_key} в golden set)")

    # сохраняем miss-лог (даже пустой — пустой лог тоже информация: «промахов нет»)
    log_path = f"miss_{collection_name}_{type}_k{top_k}.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(misses, f, ensure_ascii=False, indent=2)

    # ЕДИНСТВЕННАЯ точка выхода — dict возвращается всегда
    return {
        "collection": collection_name,
        "type": type,
        "k": top_k,
        "hit_rate": hits / valid,
        "mrr": rr_sum / valid,
        "hits": hits,
        "total": valid,
    }

if __name__ == "__main__":

    golden_path = DATA_DIR / "golden_set_mapped.json"
    if not golden_path.exists():
        golden_path = DATA_DIR / "golden_set.json"

    if not golden_path.exists():
            raise FileNotFoundError(
                f"Файл датасета не найден ни по пути {DATA_DIR / 'golden_set_mapped.json'}, "
                f"ни {DATA_DIR / 'golden_set.json'}. Сначала запустите скрипт генерации датасета!"
            )
    with open(golden_path, "r", encoding="utf-8") as f:
        golden_set = json.load(f)



    rows = []
    for collection, ctype in CONFIGS:
        for k in (1, 5):
            rows.append(evaluate_retrieval(collection, golden_set, ctype, top_k=k))
    print_summary(rows)
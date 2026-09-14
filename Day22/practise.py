# -*- coding: utf-8 -*-


import time
import numpy as np
from usearch.index import Index

# ----------------------- настройки эксперимента -----------------------
N = 100_000      # размер базы
DIM = 128        # размерность векторов (как в туториале Zilliz)
NQ = 100         # число запросов
K = 10           # сколько ближайших соседей ищем
M = 16           # HNSW: связей на узел (точность/память графа)
EF_CONSTRUCTION = 50  # HNSW: тщательность построения

rng = np.random.default_rng(42)
# centers = rng.normal(size=(100, DIM)).astype(np.float32)
# data = centers[rng.integers(0, 100, N)] + 0.1 * rng.normal(size=(N, DIM)).astype(np.float32)
data = rng.normal(size=(N, DIM)).astype(np.float32)
queries = rng.normal(size=(NQ, DIM)).astype(np.float32)

# ----------------------- 1. brute force (эталон) -----------------------
print("1) Brute force (точный поиск)...")
t0 = time.perf_counter()
# Квадрат евклидова расстояния: ||q - x||^2 = ||q||^2 + ||x||^2 - 2*q·x
d2 = (queries**2).sum(axis=1, keepdims=True) \
     + (data**2).sum(axis=1) - 2.0 * queries @ data.T
true_idx = np.argpartition(d2, K, axis=1)[:, :K]
t_brute = (time.perf_counter() - t0) / NQ
print(f"   время на запрос: {t_brute*1000:.1f} мс   (эталон 100% recall)\n")

# ----------------------- 2. строим HNSW -----------------------
print(f"2) Строим HNSW (M/connectivity={M}, efConstruction/expansion_add={EF_CONSTRUCTION})...")
t0 = time.perf_counter()
index = Index(
    ndim=DIM,
    metric="l2sq",                    # квадрат евклидова расстояния
    connectivity=M,                   # = M
    expansion_add=EF_CONSTRUCTION,    # = efConstruction
)
keys = np.arange(N)
index.add(keys, data)                 # инкрементальные вставки — без "обучения"
t_build = time.perf_counter() - t0
print(f"   индекс построен за {t_build:.2f} с\n")

# ----------------------- 3. поиск и recall -----------------------
def measure(ef):
    """Ищем K соседей через HNSW с заданным ef; возвращаем (мс/запрос, recall@K)."""
    index.expansion_search = ef       # = efSearch; крутится БЕЗ переиндексации
    t0 = time.perf_counter()
    matches = index.search(queries, K)
    t = (time.perf_counter() - t0) / NQ
    approx_idx = matches.keys        # (NQ, K) — ключи найденных соседей
    hits = sum(len(set(a) & set(t)) for a, t in zip(approx_idx, true_idx))
    return t * 1000, hits / (NQ * K)

print("3) Крутим efSearch — компромисс скорость/точность:")
print(f"   {'efSearch':>8} | {'мс/запрос':>9} | {'recall@10':>9} | ускорение vs brute force")
print("   " + "-" * 62)
for ef in [10, 20, 50, 100, 200, 400]:
    ms, rec = measure(ef)
    print(f"   {ef:>8} | {ms:>8.3f} | {rec:>9.1%} | в {t_brute*1000/ms:>5.0f} раз")


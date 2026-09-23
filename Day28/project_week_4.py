import argparse
import json
import os
from pathlib import Path

import openai
from openai import OpenAI
import anthropic
from anthropic import Anthropic
from dotenv import load_dotenv, find_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (Prefetch, FusionQuery, Fusion, SparseVector,
                                  Filter, FieldCondition, MatchValue)
from sentence_transformers import SentenceTransformer, CrossEncoder
from fastembed import SparseTextEmbedding
from tqdm import tqdm

# --- Конфигурация -----------------------------------------------------------
OPENAI_MODEL = "gpt-4o-mini"
ANTHROPIC_MODEL = "claude-opus-5"

load_dotenv(find_dotenv())
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
model = SentenceTransformer("intfloat/e5-base-v2")
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
client = QdrantClient(url="http://localhost:6333")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'


history = []

FALLBACK_MSG = "В документах нет информации по этому вопросу."

template = '''You are a search engine. You will be provided with some retrieved context, as well as the user query.

Your job is to understand the query and answer based ONLY on the retrieved context. If you can't find the answer, you can say "I dont know".

Requirements for your answer:
1. After EVERY fact, cite the source in brackets right after it, including the file,
   the page (if present in the context header) and the section,
   e.g. (Attention_(machine_learning).pdf, page 3, section "Legend").
2. After each citation, quote the EXACT sentence from the context that supports the fact.
3. Base every fact strictly on the provided context. Do not invent anything.

Here is context:

<context>

{context}

</context>

Question: {question}
'''


def hybrid_search(query: str, collection: str, limit: int = 5, source: str = None):
    search_filter = None
    if source:
        search_filter = Filter(
            must=[
                FieldCondition(
                    key="source",  
                    match=MatchValue(value=source)
                )
            ]
        )
    dense_q = model.encode(["query: " + query], normalize_embeddings=True)[0].tolist()
    sparse_q = list(sparse_model.embed([query]))[0]

    return client.query_points(
        collection_name=collection,
        prefetch=[
            Prefetch(
                query=dense_q,
                using="dense",
                limit=limit,
                filter=search_filter
            ),
            Prefetch(
                query=SparseVector(
                    indices=sparse_q.indices.tolist(),
                    values=sparse_q.values.tolist()),
                using="sparse",
                limit=limit,
                filter=search_filter
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=limit,
    ).points


def hybrid_search_reranked(query: str, collection: str, k_final: int = 5,
                           k_candidates: int = 20, source: str = None):
    candidates = hybrid_search(query, collection, limit=k_candidates, source=source)
    if not candidates:
        return []

    pairs = [(query, c.payload["text"]) for c in candidates]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return ranked[:k_final]


def build_context(results):
    parts = []
    for rec, score in results:
        payload = rec.payload

        source = payload.get("source", "N/A")
        section = payload.get("section", "N/A")
        page = payload.get("page")
        text = payload.get("text", "")

        page_str = f", page {page}" if page is not None else ""
        parts.append(
            f"[Source: {source}{page_str}, section {section}]\n{text}"
        )
    return "\n\n---\n\n".join(parts)


def evaluate_retrieval(collection_name, golden_set, top_k):
    """Считает Recall@k и MRR отдельно для ретривера и для реранкера —
    так видно, на каком этапе теряются документы."""
    expected_key = "expected_ids_512"

    stats = {
        "retriever": {"hits": 0, "rr": 0.0},
        "reranked":  {"hits": 0, "rr": 0.0},
    }
    valid = 0
    hit_scores = []
    miss_scores = []

    for q in tqdm(golden_set, desc=f"{collection_name}"):
        if q.get("is_negative"):
            continue
        expected_ids = q.get(expected_key)
        if not expected_ids:
            continue
        valid += 1

        # 1) чистый ретривер (dense + BM25 + RRF), top-k без реранкинга
        retr_points = hybrid_search(q["question"], collection_name, limit=top_k)
        retr_ids = [p.payload["chunk_id"] for p in retr_points]

        # 2) ретривер + кросс-энкодер
        rer_results = hybrid_search_reranked(q["question"], collection_name,
                                             k_final=top_k, k_candidates=20)
        rer_ids = [c.payload["chunk_id"] for c, _ in rer_results]

        for name, ids in (("retriever", retr_ids), ("reranked", rer_ids)):
            for rank, rid in enumerate(ids, start=1):
                if rid in expected_ids:
                    stats[name]["hits"] += 1
                    stats[name]["rr"] += 1.0 / rank
                    break

        # скоры реранкера — для калибровки порога fallback
        hit_rank = next((r for r, rid in enumerate(rer_ids, 1) if rid in expected_ids), None)
        if hit_rank is not None:
            hit_scores.append(rer_results[hit_rank - 1][1])
        elif rer_results:
            miss_scores.append(rer_results[0][1])

    if valid == 0:
        raise ValueError(f"{collection_name}: ни одного валидного вопроса "
                         f"(проверь {expected_key} в golden set)")

    print("\n\n--- АНАЛИЗ ДЛЯ ПОДБОРА ПОРОГА (SCORES) ---")
    if hit_scores:
        print(f"✅ ПРАВИЛЬНЫЕ документы: min = {min(hit_scores):.4f} | avg = {sum(hit_scores)/len(hit_scores):.4f}")
    if miss_scores:
        print(f"❌ ПРОМАХИ (лучший скор мусора): max = {max(miss_scores):.4f} | avg = {sum(miss_scores)/len(miss_scores):.4f}")
    print("Порог (--threshold) ставьте между max промахов и min правильных.")
    print("------------------------------------------")

    return [
        {"collection": f"{collection_name} [retriever]", "k": top_k,
         "hit_rate": stats["retriever"]["hits"] / valid,
         "mrr": stats["retriever"]["rr"] / valid,
         "hits": stats["retriever"]["hits"], "total": valid},
        {"collection": f"{collection_name} [reranked]", "k": top_k,
         "hit_rate": stats["reranked"]["hits"] / valid,
         "mrr": stats["reranked"]["rr"] / valid,
         "hits": stats["reranked"]["hits"], "total": valid},
    ]


def check_negatives(collection_name, golden_set, threshold):
    """Прогоняет негативные вопросы: fallback должен сработать на каждом.
    Печатает топ-скор реранкера по каждому — это «мусорные» скоры,
    выше которых должен стоять порог."""
    negatives = [q for q in golden_set if q.get("is_negative")]
    if not negatives:
        print("В golden-set нет негативных вопросов (is_negative).")
        return

    print(f"\n--- НЕГАТИВНЫЕ ВОПРОСЫ (порог = {threshold}) ---")
    caught = 0
    for q in negatives:
        results = hybrid_search_reranked(q["question"], collection_name,
                                         k_final=5, k_candidates=20)
        top = results[0][1] if results else float("-inf")
        blocked = top < threshold
        caught += blocked
        mark = "✅ fallback" if blocked else "❌ ПРОПУЩЕН"
        print(f"{mark} | top_score = {top:>8.4f} | {q['question'][:70]}")
    print(f"Итого: {caught}/{len(negatives)} отклонено. "
          f"Порог должен быть выше max скора негативных, "
          f"но ниже min скора правильных из /eval.")


def openai_stream(question: str, collection: str, source: str = None,
                  threshold: float = 0.1):
    results = hybrid_search_reranked(question, collection, source=source)

    if not results or results[0][1] < threshold:
        yield FALLBACK_MSG
        return

    context = build_context(results)
    prompt = template.format(context=context, question=question)
    history.append({"role": "user", "content": prompt})
    full_response = ""
    stream = None
    try:
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        stream = openai_client.responses.create(
            model=OPENAI_MODEL,
            input=messages,
            stream=True
        )
        for chunk in stream:
            if chunk.type == "response.output_text.delta":
                text_delta = chunk.delta
                if text_delta:
                    full_response += text_delta
                    yield text_delta
            elif chunk.type == "response.completed":
                usage = chunk.response.usage
                if usage:
                    print(f"\n[tokens: in={usage.input_tokens} out={usage.output_tokens}]")

    except openai.RateLimitError as e:
        print(f"\n[429 Rate Limit] Лимит запросов: {e.message}. Подождите и повторите.")
    except (openai.APIConnectionError, openai.APITimeoutError) as e:
        print(f"\n[Сеть/таймаут] Проблема с соединением к OpenAI: {e}")
    except openai.APIError as e:
        print(f"\n[API Error OpenAI {e.status_code}] {e.message}")
    except Exception as e:
        print(f"\n[Системная ошибка] {type(e).__name__}: {e}")
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
    if full_response:
        history.append({"role": "assistant", "content": full_response})
    else:
        history.pop()


def anthropic_stream(question: str, collection: str, source: str = None,
                     threshold: float = 0.1):
    results = hybrid_search_reranked(question, collection, source=source)

    if not results or results[0][1] < threshold:
        yield FALLBACK_MSG
        return

    context = build_context(results)
    prompt = template.format(context=context, question=question)
    history.append({"role": "user", "content": prompt})
    full_response = ""
    try:
        with anthropic_client.messages.stream(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            messages=[{"role": m["role"], "content": m["content"]} for m in history],
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                yield text
            final = stream.get_final_message()
            if final and final.usage:
                print(f"\n[tokens: in={final.usage.input_tokens} out={final.usage.output_tokens}]")

    except anthropic.RateLimitError as e:
        print(f"\n[429 Rate Limit] Лимит запросов: {e.message}. Подождите и повторите.")
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
        print(f"\n[Сеть/таймаут] Проблема с соединением к Anthropic: {e}")
    except anthropic.APIError as e:
        print(f"\n[API Error Anthropic {e.status_code}] {e.message}")
    except Exception as e:
        print(f"\n[Системная ошибка] {type(e).__name__}: {e}")
    finally:
        if full_response:
            history.append({"role": "assistant", "content": full_response})
        else:
            history.pop()


def print_summary(rows):
    print("\n" + "=" * 66)
    print(" СВОДНАЯ ТАБЛИЦА")
    print("=" * 66)
    print(f"{'Коллекция':<30}{'k':>3}{'R@k':>8}{'MRR':>8}{'hits':>10}")
    print("-" * 66)
    for r in rows:
        print(f"{r['collection']:<30}{r['k']:>3}"
              f"{r['hit_rate']:>7.1%}{r['mrr']:>8.4f}"
              f"{r['hits']:>6}/{r['total']}")
    print("-" * 66)


def print_help(source, threshold):
    print("\nКоманды:")
    print("  /source <файл>  — фильтр по источнику (без аргумента — сбросить)")
    print(f"  /threshold <N>  — порог реранкера для fallback (сейчас: {threshold})")
    print("  /eval           — прогнать golden-set (Recall@5 и MRR)")
    print("  /negcheck       — проверить fallback на негативных вопросах")
    print("  /help           — эта справка")
    print("  exit / quit     — выход")
    print(f"Текущий фильтр источника: {source or '(нет)'}")


def main():
    parser = argparse.ArgumentParser(description="CLI Chat SDK")
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic"],
        default="openai",
        help="Выбор провайдера"
    )
    parser.add_argument(
        "--source",
        default="",
        help="Фильтр по источнику (имя файла из payload)"
    )
    # ms-marco-MiniLM-L-6-v2 возвращает сырые логиты (примерно -10..+10),
    # а не вероятности 0..1. Подберите порог по выводу /eval.
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.1,
        help="Минимальный скор реранкера, ниже — fallback «нет информации»"
    )
    args = parser.parse_args()
    provider = args.provider
    source = args.source or None
    threshold = args.threshold

    collection_name = "week_4_project"
    golden_path = DATA_DIR / "golden_set_mapped.json"
    if not golden_path.exists():
        golden_path = DATA_DIR / "golden_set.json"
    print(f"--- Чат запущен (provider={provider}, threshold={threshold}) ---")
    print_help(source, threshold)

    while True:
        try:
            user_input = input("\nВы: ").strip()
            if not user_input:
                continue

            low = user_input.lower()
            if low in ["exit", "quit"]:
                print("Завершение сеанса...")
                break

            if low.startswith("/source"):
                parts = user_input.split(maxsplit=1)
                source = parts[1].strip() if len(parts) > 1 else None
                print(f"Фильтр источника: {source or '(сброшен)'}")
                continue

            if low.startswith("/threshold"):
                parts = user_input.split(maxsplit=1)
                try:
                    threshold = float(parts[1])
                    print(f"Порог fallback: {threshold}")
                except (IndexError, ValueError):
                    print("Использование: /threshold 1.5")
                continue

            if low == "/eval":
                with open(golden_path, "r", encoding="utf-8") as f:
                    golden_set = json.load(f)
                rows = evaluate_retrieval(collection_name, golden_set, top_k=5)
                print_summary(rows)
                continue

            if low == "/negcheck":
                with open(golden_path, "r", encoding="utf-8") as f:
                    golden_set = json.load(f)
                check_negatives(collection_name, golden_set, threshold)
                continue
            
            if low == "/help":
                print_help(source, threshold)
                continue

            if provider == "openai":
                stream = openai_stream(user_input, collection_name,
                                       source=source, threshold=threshold)
            else:
                stream = anthropic_stream(user_input, collection_name,
                                          source=source, threshold=threshold)
            for chunk in stream:
                print(chunk, end="", flush=True)

            print()

        except (KeyboardInterrupt, EOFError):
            print("\nСеанс прерван.")
            break


if __name__ == '__main__':
    main()
from openai import OpenAI
from dotenv import load_dotenv,find_dotenv
from rank_bm25 import BM25Okapi
import openai
import json,uuid
from sentence_transformers import SentenceTransformer,CrossEncoder
# import argparse
import os
import numpy as np
import re

load_dotenv(find_dotenv())

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

NAMESPACE = uuid.NAMESPACE_URL



model = SentenceTransformer("intfloat/multilingual-e5-small")
cross_model = CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")






template = '''You are a search engine. You will be provided with some retrieved context, as well as the user query.

Your job is to understand the query and answer based ONLY on the retrieved context. If you can't find the answer, you can say "I dont know".

Requirements for your answer:
1. Always include the source file and page/chunk information in your response (for example: "04_cooking_italian.pdf, чанк 1" or "[04_cooking_italian.pdf, стр. 1]").
2. Base every fact directly on the provided context metadata.

Here is context:

<context>

{context}

</context>

Question: {question}
'''
history = []

def build_context(results):
    parts = []
    for rec, score in results:
        parts.append(
            f"[Источник: {rec['source']}, стр. {rec['page']}]\n{rec['text']}"
        )
    return "\n\n---\n\n".join(parts)


def load_bm25_index():
    chunks = [json.loads(l) for l in open("Day21/OUTPUT/chunks.jsonl", encoding="utf-8")]
    ids = [c["id"] for c in chunks]
    texts = [c["text"] for c in chunks]
    tokenized = [re.findall(r"\w+", t.lower()) for t in texts]
    id2chunk = {c["id"]: c for c in chunks}
    return ids, BM25Okapi(tokenized),id2chunk

def bm25_ranking(query, ids, bm25, top_k=20):
    scores = bm25.get_scores(re.findall(r"\w+", query.lower()))
    top_idx = np.argsort(-np.asarray(scores))[:top_k]
    return [ids[i] for i in top_idx]

def load_dense_index():
  
    rows = [json.loads(l) for l in open("Day21/OUTPUT/index.jsonl", encoding="utf-8")]
    ids = [r["id"] for r in rows]
    matrix = np.array([r["vector"] for r in rows], dtype=np.float32)  
    return ids, matrix




def dense_ranking(query: str, ids, matrix, top_k=20):
    """Возвращает список id, лучший первый."""
    q = model.encode_query(query)                     
    q = q / np.linalg.norm(q)
    M = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    scores = M @ q                                   
    top_idx = np.argsort(-scores)[:top_k]
    return [ids[i] for i in top_idx]

def rrf(list_a, list_b, k=60):
    scores = {}
    for ranking in (list_a, list_b):
        for rank, doc_id in enumerate(ranking):      # rank с нуля → 1/(k+rank+1)
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)

def retrieve(question, bm25_ids,bm25,dense_ids, matrix,id2chunk, top_k = 20, top = 3):
   
    bm25_r = bm25_ranking(question,bm25_ids,bm25, top_k)
    dense_r = dense_ranking(question, dense_ids, matrix, top_k)
    rrf_res = rrf(bm25_r, dense_r)
    shortlist = rrf_res[:top_k]
    cross_input = [[question, id2chunk[doc_id]["text"]] for doc_id in shortlist]
    cross_scores = cross_model.predict(cross_input)
    
    print("BM25:  ", bm25_r[:3])
    print("Dense: ", dense_r[:3])
    print("RRF:   ", rrf_res[:3])
    reranked_results = []
    for doc_id, score in zip(shortlist, cross_scores):
        reranked_results.append((id2chunk[doc_id], float(score)))
        
    reranked_results.sort(key=lambda x: x[1], reverse=True)
    
    return reranked_results[:top]


def get_response(question:str, data):




    results = retrieve(question, data["bm25_ids"], data["bm25"], data["dense_ids"],data["matrix"] , data["id2chunk"])
    print(f"[debug] top-3 после реранка: {[(r[0]['id'], round(r[1],2)) for r in results]}")
    # if results[0][1] < 0.35:        
    #     print("В документах нет информации по этому вопросу.")
    #     return
    # вызов LLM с контекстом
    context = build_context(results)
    prompt = template.format(context=context, question=question)
    history.append({"role": "user", "content": prompt})
    full_response = ""
    stream = None
    try: 
        messages =  [
            {"role": m["role"], "content": m["content"]} for m in history
        ]
        stream = openai.responses.create(
            model="gpt-4o-mini",
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
                final_usage = chunk.response.usage

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



def main():
    bm25_ids, bm25,id2chunk = load_bm25_index()
    dense_ids, matrix = load_dense_index()

    data = {
        "bm25_ids" :bm25_ids,
        "bm25" :bm25,
        "id2chunk" :id2chunk,
        "dense_ids" :dense_ids,
        "matrix" :matrix,
    }
    


    print(f"--- Чат запущен ---")
    print("Команды: exit/quit")

    while True:
        try:
            user_input = input("\nВы: ").strip()
            if user_input.lower() in ["exit", 'quit']:
                print("Завершение сеанса...")
                break
            if not user_input:
                continue
            stream = get_response(user_input, data)
            for chunk in stream:
                print(chunk, end="", flush=True)       

            print()

        except (KeyboardInterrupt,EOFError):
            print("\nСеанс прерван.")
            break         


if __name__ == "__main__":
    main()
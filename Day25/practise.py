from openai import OpenAI
from dotenv import load_dotenv,find_dotenv
from qdrant_client import QdrantClient
import numpy as np

import openai
import json,uuid
from sentence_transformers import SentenceTransformer
# import argparse
import os
load_dotenv(find_dotenv())

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
qbrant_client = QdrantClient(url="http://localhost:6333")
NAMESPACE = uuid.NAMESPACE_URL
model = SentenceTransformer("intfloat/multilingual-e5-small")
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


records = [json.loads(l) for l in open("Day21/OUTPUT/index.jsonl",encoding="utf-8")]
vectors = np.array([r["vector"] for r in records]) 
history = []

def retrieve(query: str, top_k: int = 3):
    q = model.encode(query)       
    scores = vectors @ q / np.linalg.norm(q) 
    top = np.argpartition(-scores, top_k)[:top_k]
    return [(records[i], float(scores[i])) for i in top]

def build_context(results):
    parts = []
    for rec, score in results:
        parts.append(
            f"[Источник: {rec['source']}, стр. {rec['page']}]\n{rec['text']}"
        )
    return "\n\n---\n\n".join(parts)

def get_response(question:str):

    results = retrieve(question, top_k=3)
    if results[0][1] < 0.35:        
        print("В документах нет информации по этому вопросу.")
    else:
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
    # parser = argparse.ArgumentParser(description="CLI Chat SDK")
  
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
            stream = get_response(user_input)
            for chunk in stream:
                print(chunk, end="", flush=True)       

            print()

        except (KeyboardInterrupt,EOFError):
            print("\nСеанс прерван.")
            break         




if __name__ == "__main__":
    main()
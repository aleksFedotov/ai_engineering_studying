from openai import OpenAI
from dotenv import load_dotenv
import os   
from sentence_transformers import SentenceTransformer
from openai.types import CreateEmbeddingResponse
import numpy as np
import pandas as pd
import time 
load_dotenv("../.env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

model = SentenceTransformer("intfloat/multilingual-e5-small")

phrase = 'Кошка спит на диване'

pairs = [("банк реки", "банк денег"),
         ("кошка спит на диване", "кот отдыхает дома"),
         ("как приготовить борщ", "курс евро сегодня")]

texts = [t for pair in pairs for t in pair]

def print_table(table, index, columns):
    df = pd.DataFrame(table, index, columns)
    print(df.round(3))

    
def get_open_ai_response(text: str | list[str]):
    res = client.embeddings.create(
    model="text-embedding-3-small",
    input=text,
    encoding_format="float",
    )

    return res

def create_similarity_table_loop( res: CreateEmbeddingResponse):
    data = res.data
    n = len(data)
    table = np.zeros((n, n))
    for i in range(n):
        for j in range(i, n):  # только верхний треугольник
            s = np.dot(data[i].embedding, data[j].embedding)
            table[i, j] = table[j, i] = s 

    return table

def create_similarity_table_np( res: CreateEmbeddingResponse) -> np.ndarray:
    vecs = np.array([d.embedding for d in res.data])  
    return vecs @ vecs.T  
        
def get_demensions(phrase: str):

    res = get_open_ai_response(phrase)
    vector_openai = res.data[0].embedding

    print(f"Размерность вектора у openaai {len(vector_openai)}")

    embeddings = model.encode(phrase, normalize_embeddings=True)
    vector_length_local = embeddings.shape[0]
    print(f"Размерность вектора у локальной {vector_length_local}")


def get_similarity(text:list[str]):

    res = get_open_ai_response(text)

    table = create_similarity_table_np(res)
    print("------------OPENAI SIMILIARITY-----------------")
    print_table(table, text, text)
    print("------------LOCAL SIMILIARITY-----------------")
    embeddings = model.encode(text, normalize_embeddings=True)
    similiarity_local = model.similarity(embeddings,embeddings)
    print_table(similiarity_local, text,text)



def batching_time(text:list[str]): 
    start_time_openai_without_batchig = time.perf_counter()
    for t in text:
        get_open_ai_response(t)
    end_time_openai_without_batchig = time.perf_counter()
    total_time_openai_without_batchig = end_time_openai_without_batchig - start_time_openai_without_batchig

    start_time_openai_with_batchig = time.perf_counter()
    get_open_ai_response(text)
    end_time_openai_with_batchig = time.perf_counter()
    total_time_openai_with_batchig = end_time_openai_with_batchig - start_time_openai_with_batchig

    start_time_local_without_batchig = time.perf_counter()
    for t in text:
        model.encode(t, normalize_embeddings=True)
    end_time_local_without_batchig = time.perf_counter()
    total_time_local_without_batchig = end_time_local_without_batchig - start_time_local_without_batchig

    start_time_local_with_batchig = time.perf_counter()
    model.encode(text, normalize_embeddings=True)
    end_time_local_with_batchig = time.perf_counter()
    total_time_local_with_batchig = end_time_local_with_batchig - start_time_local_with_batchig

    print("-------------------OPENAI TIME-------------------")
    print(f"TIME WITHOUT BATCHING [{total_time_openai_without_batchig:.3f}s] | TIME WITH BATCHING [{total_time_openai_with_batchig:.3f}s]")
    print("-------------------LOCAL TIME-------------------")
    print(f"TIME WITHOUT BATCHING [{total_time_local_without_batchig:.3f}s] | TIME WITH BATCHING [{total_time_local_with_batchig:.3f}s]")

 


def main():
    get_demensions(phrase)
    get_similarity(texts)
    batching_time(texts)

if __name__ == "__main__":
    main()
    

from openai import OpenAI
from dotenv import load_dotenv
import os   
from sentence_transformers import SentenceTransformer
import numpy as np


model = SentenceTransformer("intfloat/multilingual-e5-large")

texts = [
    "банк реки",
    "банк денег",
    "кошка спит на диване",
    "кот отдыхает дома",
    "как приготовить борщ",
    "курс евро сегодня",
]

long_texts= [
    "мы стояли на высоком банке реки и ловили рыбуи",
    "я пришёл в банк, чтобы открыть вклад",
    "кошка спит на диване",
    "кот отдыхает дома",
    "как приготовить борщ",
    "курс евро сегодня",
]

emb = model.encode(["query: " + t for t in texts], normalize_embeddings=True)
emb_without_query = model.encode(texts, normalize_embeddings=True)
sim = emb @ emb.T
sim_without_query = emb_without_query @ emb_without_query.T
np.set_printoptions(precision=3, suppress=True)
for i, t in enumerate(texts):
    print(i, t)
print("-----With query-------")
print(sim)
print("-----Without query-------")
print(sim_without_query)
emb_long = model.encode(["query: " + t for t in long_texts], normalize_embeddings=True)
sim_long = emb_long @ emb_long.T
for i, t in enumerate(long_texts):
    print(i, t)
print("-----With query and long phrases-------")
print(sim_long)

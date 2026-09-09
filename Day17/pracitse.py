import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from openai import OpenAI
from sklearn.manifold import TSNE
import umap

# 1. Загрузка данных и кэша
load_dotenv('../.env')
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

df = pd.read_csv("тексты_4_темы.csv")
texts = df['text'].tolist()

CACHE_FILE = "embeddings.npy"
if os.path.exists(CACHE_FILE):
    matrix = np.load(CACHE_FILE)
else:
    response = client.embeddings.create(model="text-embedding-3-small", input=texts)
    matrix = np.array([item.embedding for item in response.data])
    np.save(CACHE_FILE, matrix)

# 2. Универсальная функция отрисовки на графике-подложке (ax)
def draw_cluster_plot(ax, array, title, df):
    x = array[:, 0]
    y = array[:, 1]
    unique_topics = df['topic'].unique()
    colors = ["red", "darkorange", "gold", "turquoise"]

    for i, topic in enumerate(unique_topics):
        mask = df['topic'] == topic
        color = colors[i % len(colors)]
        
        # Точки
        ax.scatter(x[mask], y[mask], color=color, label=topic, alpha=0.6, edgecolors='w')
        
        # Центроид
        avg_x = x[mask].mean()
        avg_y = y[mask].mean()
        ax.scatter(avg_x, avg_y, marker='X', color=color, s=120, linewidths=2, edgecolors='black')

    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.legend(title="Темы", fontsize=8)
    ax.grid(True, linestyle='--', alpha=0.3)

# ==========================================
# ЭКСПЕРИМЕНТ 1: t-SNE (Перебор perplexity)
# ==========================================
perplexities = [5, 10, 15, 20]
fig_tsne, axes_tsne = plt.subplots(2, 2, figsize=(14, 10))
axes_tsne = axes_tsne.flatten() # Распаковываем матрицу 2x2 в 1D список из 4 осей

for idx, perp in enumerate(perplexities):
    tsne = TSNE(n_components=2, perplexity=perp, random_state=42, init='random', learning_rate=200)
    vis_tsne = tsne.fit_transform(matrix)
    draw_cluster_plot(axes_tsne[idx], vis_tsne, f"t-SNE: perplexity={perp}", df)

fig_tsne.suptitle("Эксперименты с t-SNE (Влияние Perplexity)", fontsize=16, y=1.02)
plt.tight_layout()

# ==========================================
# ЭКСПЕРИМЕНТ 2: UMAP (n_neighbors + min_dist)
# ==========================================
umap_configs = [
    {"n_neighbors": 5,  "min_dist": 0.0},
    {"n_neighbors": 5,  "min_dist": 0.5},
    {"n_neighbors": 30, "min_dist": 0.0},
    {"n_neighbors": 30, "min_dist": 0.5},
]

fig_umap, axes_umap = plt.subplots(2, 2, figsize=(14, 10))
axes_umap = axes_umap.flatten()

for idx, cfg in enumerate(umap_configs):
    n_n = cfg["n_neighbors"]
    m_d = cfg["min_dist"]
    
    reducer = umap.UMAP(n_neighbors=n_n, min_dist=m_d, metric='cosine', random_state=42, n_jobs=1)
    vis_umap = reducer.fit_transform(matrix)
    draw_cluster_plot(axes_umap[idx], vis_umap, f"UMAP: n_neighbors={n_n}, min_dist={m_d}", df)

fig_umap.suptitle("Эксперименты с UMAP (n_neighbors vs min_dist)", fontsize=16, y=1.02)
plt.tight_layout()

# Отобразить оба окна с сетками
plt.show()
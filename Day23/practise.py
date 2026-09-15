import chromadb
from pathlib import Path
import json
current_dir = Path(__file__).resolve().parent
file_path = current_dir.parent / "Day21" / "OUTPUT" / "index.jsonl"
from sentence_transformers import SentenceTransformer

chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="my_collection")
model = SentenceTransformer("intfloat/multilingual-e5-small")
# chunks = []
# with open(file_path, encoding="utf-8") as f:
#     for line in f:
#         chunks.append(json.loads(line))



# ids = []
# embeddings =[]
# documents = []
# metadatas = []
# for idx, chunk in enumerate(chunks):
   
#     ids.append(str(chunk['id']))
#     documents.append(chunk["text"]) 
#     embeddings.append(chunk["vector"])
#     metadatas.append({
#             "source": chunk.get("source", ""),
#             "page": chunk.get("page", 0),
#             "chunk_index": chunk.get("chunk_index", 0)
#         })

# collection.add(
#     ids=ids,
#     embeddings=embeddings,
#     documents=documents,
#     metadatas=metadatas
   
# )

chunks = [json.loads(l) for l in open("Day21/OUTPUT/index.jsonl", encoding="utf-8")]
collection.add(
    ids=[str(c["id"]) for c in chunks],
    documents=[c["text"] for c in chunks],
    embeddings=[c["vector"] for c in chunks],
    metadatas=[{"source": c.get("source", "")} for c in chunks],
)
def search(query:str, n:int =5):
    
    target_vector = model.encode(query, batch_size=32, show_progress_bar=True, prompt_name='query').tolist()
    results = collection.query(
        query_embeddings=[target_vector],
        n_results=n
    )
    return results
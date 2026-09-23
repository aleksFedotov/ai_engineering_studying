from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct,SparseVector,SparseVectorParams,SparseIndexParams
import json, uuid
from pathlib import Path
from fastembed import SparseTextEmbedding; 
from sentence_transformers import SentenceTransformer


model = SentenceTransformer("intfloat/e5-base-v2")
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
client = QdrantClient(url="http://localhost:6333")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR =  BASE_DIR / 'data'

COLLECTION_NAME = 'week_4_project'

def create_hybrid_collection(collection_name: str, size: int):
    if client.collection_exists(collection_name):
        client.delete_collection(collection_name)   
    client.create_collection(
        collection_name=collection_name,
        vectors_config={"dense": VectorParams(size=size, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams())},
    )


def build_hybrid_index(path:str, name: str, size:int):
    create_hybrid_collection(name, size)
    docs = [json.loads(l) for l in open(path, encoding="utf-8")]
    texts = [d["text"] for d in docs]

    dense_vecs = model.encode(["passage: " + t for t in texts],
                              normalize_embeddings=True, batch_size=64)
    sparse_vecs = list(sparse_model.embed(texts))   

    points = []
    for d, dv, sv in zip(docs, dense_vecs, sparse_vecs):
        points.append(PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, d["id"])),
            vector={
                "dense": dv.tolist(),
                "sparse": SparseVector(
                    indices=sv.indices.tolist(),
                    values=sv.values.tolist(),
                ),
            },
            payload={"source": d["source"], "section": d["section"],
                     "chunk_index": d["chunk_index"], "text": d["text"],
                     "chunk_id": d["id"]},
        ))

    for i in range(0, len(points), 256):
        client.upsert(collection_name=name, points=points[i:i+256], wait=True)




def main():
    path = DATA_DIR / "chunks_512.jsonl"
 
    build_hybrid_index(path,COLLECTION_NAME, 768 )

    print(client.count(COLLECTION_NAME)) 




if __name__ == "__main__":
    main()
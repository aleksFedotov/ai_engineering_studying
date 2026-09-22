from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct,SparseVector,SparseVectorParams,SparseIndexParams
import json, uuid
from pathlib import Path
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding; 

model = SentenceTransformer("intfloat/e5-base-v2")
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

NAMESPACE = uuid.NAMESPACE_URL
client = QdrantClient(url="http://localhost:6333")
COLLECTION_512 = "chunks_512"
COLLECTION_256 = "chunks_256"
COLLECTION_512_HYBRID = "chunks_512_hybrid"
COLLECTION_256_HYBRID = "chunks_256_hybrid"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

def create_collection(collection_name:str, size: int):

    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),
        )

def create_hybrid_collection(collection_name: str, size: int):
    if client.collection_exists(collection_name):
        client.delete_collection(collection_name)   # старая схема не подходит
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


def build_index(path:str, name:str, size : int):
    create_collection(name, size)
    docs = [json.loads(l) for l in open(path, encoding="utf-8")]
    texts = ["passage: " + d["text"] for d in docs]      
    vectors = model.encode(texts, batch_size=64, show_progress_bar=True,
                           normalize_embeddings=True)
    points = [
        PointStruct(
            id=str(uuid.uuid5(NAMESPACE, d["id"])),      
            vector=v.tolist(),
            payload={"source": d["source"], "section": d["section"],
                     "chunk_index": d["chunk_index"], "text": d["text"],
                     "chunk_id": d["id"]},
        )
        for d, v in zip(docs, vectors)
    ]
    for i in range(0, len(points), 256):                
        client.upsert(collection_name=name, points=points[i:i+256], wait=True)
    print(f"{name}: {len(points)} векторов")


def main():
    path_512 = DATA_DIR / "chunks_512.jsonl"
    path_256 = DATA_DIR / "chunks_256.jsonl"
    # build_index(path_512, COLLECTION_512, 768)
    # build_index(path_256, COLLECTION_256, 768)
    # print(client.count(COLLECTION_512)) 
    # print(client.count(COLLECTION_256))
    build_hybrid_index(path_512,COLLECTION_512_HYBRID, 768 )
    build_hybrid_index(path_256,COLLECTION_256_HYBRID, 768 )
    print(client.count(COLLECTION_512_HYBRID)) 
    print(client.count(COLLECTION_256_HYBRID))
    # q = model.encode(["query: In what year was the Battle of Cannae?"], normalize_embeddings=True)
    # hits = client.query_points(collection_name="chunks_512", query=q[0].tolist(), limit=5)
    # for h in hits.points:
    #     print(h.score, h.payload["chunk_id"], h.payload["text"][:100])


if __name__ == "__main__":
    main()

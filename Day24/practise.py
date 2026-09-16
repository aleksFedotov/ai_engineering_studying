from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct,Filter, FieldCondition, MatchValue
import json, uuid
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("intfloat/multilingual-e5-small")

NAMESPACE = uuid.NAMESPACE_URL
client = QdrantClient(url="http://localhost:6333")
COLLECTION = "study_docs"
if not client.collection_exists(COLLECTION):
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )
points = []
with open("Day21/OUTPUT/index.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        points.append(PointStruct(
            id=uuid.uuid5(NAMESPACE, d["id"]).hex,   # детерминированный UUID из строки
            vector=d["vector"],
            payload={
                "source": d["source"],
                "page": d["page"],
                "chunk_index": d["chunk_index"],
                "text": d["text"],
                "chunk_id": d["id"],                  # оригинальный строковый id
            },
        ))
client.upsert(collection_name=COLLECTION, points=points, wait=True)

print(client.count(collection_name=COLLECTION)) 

query_text = "как бороться с переобучением модели"
query_vector = model.encode("query: " + query_text).tolist()

res_without_query_filter = client.query_points(
    collection_name=COLLECTION,
    query=query_vector,
    limit=3,
    with_payload=True,
).points
print("-----Result without query filter-----")
for p in res_without_query_filter:
    print(round(p.score, 4), p.payload["source"], "стр.", p.payload["page"])
res_with_query_filter = client.query_points(
    collection_name=COLLECTION,
    query=query_vector,
    limit=3,
    with_payload=True,
    query_filter=Filter(
    must=[FieldCondition(key="source", match=MatchValue(value="05_finance_investing.pdf"))]
    ),
).points
print("-----Result with query filter-----")
for p in res_with_query_filter:
    print(round(p.score, 4), p.payload["source"], "стр.", p.payload["page"])
res_with_query_filter_limit_3 = client.query_points(
    collection_name=COLLECTION,
    query=query_vector,
    limit=3,
    with_payload=True,
    query_filter=Filter(
    must=[FieldCondition(key="source", match=MatchValue(value="05_finance_investing.pdf"))]
    ),
).points
print("-----Result with query filter limit 3-----")
for p in res_with_query_filter_limit_3 :
    print(round(p.score, 4), p.payload["source"], "стр.", p.payload["page"])
res_without_query_filter_limit_20 = client.query_points(
    collection_name=COLLECTION,
    query=query_vector,
    limit=20,
    with_payload=True,
).points
print("-----Result without query filter limit 20-----")
sorted_points = sorted(res_without_query_filter_limit_20, key=lambda x: x.score, reverse=True)
for p in sorted_points:

    print(round(p.score, 4), p.payload["source"], "стр.", p.payload["page"])


modified_points = []
with open('Day21/OUTPUT/index.jsonl', 'r', encoding='utf-8') as f:
    for index, line in enumerate(f, start=1):
        if index == 3:
            d = json.loads(line)
            modified_points.append(PointStruct(
                id=uuid.uuid5(NAMESPACE, d["id"]).hex,
                vector=d["vector"],
                payload={
                    "source": d["source"],
                    "page": 99,                     # <- изменённое поле
                    "chunk_index": d["chunk_index"],
                    "text": d["text"],
                    "chunk_id": d["id"],
                },
            ))

client.upsert(collection_name=COLLECTION, points=modified_points, wait=True)
print("Modified, count =", client.count(collection_name=COLLECTION).count)
res_modified = client.query_points(
    collection_name=COLLECTION,
    query=query_vector,
    limit=3,
    with_payload=True,
    query_filter=Filter(
    must=[FieldCondition(key="source", match=MatchValue(value="01_machine_learning.pdf"))]
    ),
).points
print("-----Result modified -----")
point = client.retrieve(
    collection_name=COLLECTION,
    ids=[uuid.uuid5(NAMESPACE, "01_machine_learning_chunk_2").hex],  # index==3 → третья строка
    with_payload=True,
)
print(point[0].payload["page"]) 


client.set_payload(
    collection_name=COLLECTION, 
    payload={"outdated": True}, 
    points=Filter(
        must=[
            FieldCondition(
                key="source",
                match=MatchValue(value="09_psychology_habits.pdf"),
            )
        ]
    ),
)

res = client.query_points(
    collection_name=COLLECTION,
    query=query_vector,
    limit=10,
    with_payload=True,
    query_filter=Filter(
        must=[FieldCondition(key="outdated", match=MatchValue(value=True))]
    ),
).points
print("----Outdated---")
for p in res:
    print(p.payload["source"], "outdated =", p.payload.get("outdated"))


client.delete(
    collection_name=COLLECTION, 
    points_selector= Filter(
        must=FieldCondition(key="source", match=MatchValue(value="01_machine_learning.pdf"))
    )
)

print("After deletion, count =", client.count(collection_name=COLLECTION).count)
res = client.query_points(
    collection_name=COLLECTION,
    query=query_vector,
    limit=10,
    with_payload=True,
    query_filter=Filter(
        must=[FieldCondition(key="sourse", match=MatchValue(value="01_machine_learning.pdf"))]
    ),
).points
if len(res) == 0: 
    print("01_machine_learning deleted ")



ML_points = []
with open("Day21/OUTPUT/index.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        if d["source"] == "01_machine_learning.pdf":
            ML_points.append(PointStruct(
                id=uuid.uuid5(NAMESPACE, d["id"]).hex,   # детерминированный UUID из строки
                vector=d["vector"],
                payload={
                    "source": d["source"],
                    "page": d["page"],
                    "chunk_index": d["chunk_index"],
                    "text": d["text"],
                    "chunk_id": d["id"],                  # оригинальный строковый id
                },
            ))
client.upsert(collection_name=COLLECTION, points=points, wait=True)
print("After restoration, count =", client.count(collection_name=COLLECTION).count)
res = client.query_points(
    collection_name=COLLECTION,
    query=query_vector,
    limit=10,
    with_payload=True,
    query_filter=Filter(
        must=[FieldCondition(key="source", match=MatchValue(value="01_machine_learning.pdf"))]
    ),
).points
print("----Cheking restoration")
for p in res:
    print(round(p.score, 4), p.payload["source"], "стр.", p.payload["page"])
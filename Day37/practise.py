import json
import random
import os
from openai import OpenAI
from langchain_core.documents import Document
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
import sys
import types
try:
    import langchain_community.chat_models.vertexai  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    stub_module = types.ModuleType("langchain_community.chat_models.vertexai")

    class ChatVertexAI:  # заглушка, никогда не вызывается
        pass

    stub_module.ChatVertexAI = ChatVertexAI
    sys.modules["langchain_community.chat_models.vertexai"] = stub_module
# --- конец обхода ---
from ragas.testset import TestsetGenerator
from ragas.testset.graph import KnowledgeGraph, Node, NodeType
from ragas.testset.transforms import apply_transforms
from ragas.testset.synthesizers import default_query_distribution
from ragas.llms import llm_factory
from ragas.embeddings import embedding_factory
from ragas.testset.transforms import apply_transforms, Parallel
from ragas.testset.transforms import Parallel, apply_transforms
from ragas.testset.transforms.extractors import (
    SummaryExtractor, NERExtractor, EmbeddingExtractor,
)
from ragas.testset.transforms.relationship_builders import (
    CosineSimilarityBuilder, OverlapScoreBuilder,
)


load_dotenv(find_dotenv())



client = OpenAI()  # ключ подхватится из окружения
generator_llm = llm_factory("gpt-4o-mini", client=client)
generator_embeddings = embedding_factory("openai", model="text-embedding-3-small", client=client)





current_dir = Path(__file__).parent
file_path = current_dir.parent / "data" / "wiki" / "chunks_512.jsonl"
OUT_DIR = current_dir/ "out_data"

def docs_generation(path: str | Path):
    docs = []
    print("Путь:", path.resolve())
    print("Существует:", path.exists(), "| размер:", path.stat().st_size if path.exists() else "—")
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:              # пропускаем пустые строки
                continue
            c = json.loads(line)
            docs.append(Document(
                page_content=c["text"],
                metadata ={
                    "source": c["source"],
                    "section": c["section"],
                    "chunk_id": c["id"],
                }
            ))
    print(f"Загружено чанков: {len(docs)}")
    return docs

def get_subset(total_target=250):
    docs = docs_generation(file_path)
    random.seed(42)
    by_source = {}
    for d in docs:
        by_source.setdefault(d.metadata["source"], []).append(d)

    total = len(docs)
    print(f"Источников: {len(by_source)}, всего чанков: {total}")

    docs_sample = []
    for src, group in by_source.items():
        k = max(2, round(total_target * len(group) / total))  # пропорция, минимум 2
        docs_sample.extend(random.sample(group, min(k, len(group))))

    print(f"Подвыборка: {len(docs_sample)}")
    return docs_sample


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    docs_sample = get_subset()
    print(f"Чанков в подвыборке: {len(docs_sample)}")

    kg = KnowledgeGraph()
    for doc in docs_sample:
        kg.nodes.append(Node(
            type=NodeType.DOCUMENT,
            properties={"page_content": doc.page_content,
                        "document_metadata": doc.metadata},
        ))

        trans = [
            # шаг 1: резюме каждого чанка (нужно для связей по смыслу)
            SummaryExtractor(llm=generator_llm),
            # шаг 2: эмбеддинг резюме + сущности (параллельно)
            Parallel(
                EmbeddingExtractor(
                    embedding_model=generator_embeddings,
                    property_name="summary_embedding",
                    embed_property_name="summary",
                ),
                NERExtractor(llm=generator_llm),
            ),
            # шаг 3: связи между узлами — мостики для multi-hop
            Parallel(
                CosineSimilarityBuilder(
                    property_name="summary_embedding",
                    new_property_name="summary_similarity",
                    threshold=0.5,
                ),
                OverlapScoreBuilder(threshold=0.01),
            ),
        ]
    print("До трансформаций:", kg)
    apply_transforms(kg, trans)
    print("После трансформаций:", kg)

    kg.save(OUT_DIR / "knowledge_graph.json")
    
    generator = TestsetGenerator(llm=generator_llm,
                                 embedding_model=generator_embeddings,
                                 knowledge_graph=kg)   # свежий граф уже в памяти, load не обязателен
    testset = generator.generate(testset_size=30,
                                 query_distribution=default_query_distribution(generator_llm))

    df = testset.to_pandas()
    print(df["synthesizer_name"].value_counts())

    out = df.rename(columns={
        "user_input": "question",
        "reference": "golden_answer",
        "reference_contexts": "relevant_chunks",
        "synthesizer_name": "case_type",
    })
    out["human_reviewed"] = False
    out.to_json(OUT_DIR / "eval_set_draft.jsonl",
                orient="records", lines=True, force_ascii=False)
    print("Сохранено:", OUT_DIR / "eval_set_draft.jsonl")

if __name__ == "__main__":
    main()
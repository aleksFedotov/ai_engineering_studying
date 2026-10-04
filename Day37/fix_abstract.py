
import sys
import types
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv, find_dotenv
from openai import OpenAI

try:
    import langchain_community.chat_models.vertexai  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    stub_module = types.ModuleType("langchain_community.chat_models.vertexai")

    class ChatVertexAI:
        pass

    stub_module.ChatVertexAI = ChatVertexAI
    sys.modules["langchain_community.chat_models.vertexai"] = stub_module


from ragas.testset import TestsetGenerator
from ragas.testset.graph import KnowledgeGraph
from ragas.testset.transforms import apply_transforms
from ragas.testset.transforms.extractors.llm_based import ThemesExtractor
from ragas.testset.synthesizers import MultiHopAbstractQuerySynthesizer
from ragas.llms import llm_factory
from ragas.embeddings import embedding_factory

load_dotenv(find_dotenv())

current_dir = Path(__file__).parent
OUT_DIR = current_dir / "out_data"

client = OpenAI()
generator_llm = llm_factory("gpt-4o-mini", client=client)
generator_embeddings = embedding_factory("openai", model="text-embedding-3-small", client=client)


kg = KnowledgeGraph.load(OUT_DIR / "knowledge_graph.json")
print("Граф загружен:", kg)

apply_transforms(kg, [ThemesExtractor(llm=generator_llm)])   
kg.save(OUT_DIR / "knowledge_graph.json")                   

generator = TestsetGenerator(llm=generator_llm,
                             embedding_model=generator_embeddings,
                             knowledge_graph=kg)
abstract_set = generator.generate(
    testset_size=10,
    query_distribution=[(MultiHopAbstractQuerySynthesizer(llm=generator_llm), 1.0)],
)


rename_map = {
    "user_input": "question",
    "reference": "golden_answer",
    "reference_contexts": "relevant_chunks",
    "synthesizer_name": "case_type",
}
new_rows = abstract_set.to_pandas().rename(columns=rename_map)
new_rows["human_reviewed"] = False

old_rows = pd.read_json(OUT_DIR / "eval_set_draft.jsonl", lines=True)
full = pd.concat([old_rows, new_rows], ignore_index=True)

full.to_json(OUT_DIR / "eval_set_draft.jsonl",
             orient="records", lines=True, force_ascii=False)

print(full["case_type"].value_counts())  
print("Итого строк:", len(full))
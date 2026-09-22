import json
import random
import os
import pandas as pd
from pathlib import Path
from openai import OpenAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv,find_dotenv

load_dotenv(find_dotenv())


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CHUNKS_PATH = DATA_DIR / "chunks_512.jsonl"
OUTPUT_SET = DATA_DIR / "golden_set.json"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) 


class QAWithAnchor(BaseModel):
    question: str = Field(description="Question strictly in ENGLISH based on the context.")
    ground_truth: str = Field(description="Factually accurate answer strictly in ENGLISH.")
    anchor: str = Field(description="A short, exact 3-7 word verbatim phrase copied directly from the context text that is key to the answer.")

def generate_english_qa(chunk: dict) -> QAWithAnchor | None:
    prompt = f"""
You are an expert creating a benchmark dataset for an English RAG system.
Based on the text below, generate ONE high-quality question, answer, and an anchor string.

Rules:
1. ALL output MUST be strictly in ENGLISH.
2. Question must be self-contained and natural.
3. Ground truth must be concise and based solely on the text.
4. "anchor" MUST be a short (3 to 7 words) EXACT verbatim quote from the text that appears inside the context and supports the answer.

Context (Section: {chunk.get('section', '')}):
\"\"\"
{chunk['text']}
\"\"\"
"""
    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format=QAWithAnchor,
            temperature=0.6,
        )
        return completion.choices[0].message.parsed
    except Exception as e:
        print(f"Error generating QA for {chunk['id']}: {e}")
        return None

def build_golden_set(sample_size: int = 95):
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        chunks = [json.loads(l) for l in f]

    sampled_chunks = random.sample(chunks, min(sample_size, len(chunks)))
    golden_set = []

    print(f"Generating {len(sampled_chunks)} English QA pairs...")
    for i, chunk in enumerate(sampled_chunks, 1):
        res = generate_english_qa(chunk)
        if res and res.anchor.lower() in chunk["text"].lower():
            golden_set.append({
                "id": f"q_{i:03d}",
                "question": res.question,
                "ground_truth": res.ground_truth,
                "anchor": res.anchor,
                "source": chunk["source"],
                "is_negative": False
            })
            print(f"[{i}/{len(sampled_chunks)}] OK: {res.anchor}")

    # Добавляем 5 негативных вопросов (Out-of-Domain)
    negative_questions = [
        "What is the maximum payload weight of the James Webb Space Telescope?",
        "How many total miles of fiber optic cable were laid in Tokyo during 2023?",
        "What was the main recipe ingredient for medieval Scandinavian mead in the 12th century?",
        "Which quantum computing algorithm was used by IBM to achieve quantum supremacy in 2025?",
        "What are the official rules for playing underwater rugby in the European Championship?"
    ]

    for j, neg_q in enumerate(negative_questions, 1):
        golden_set.append({
            "id": f"q_neg_{j:02d}",
            "question": neg_q,
            "ground_truth": "The provided corpus does not contain information to answer this question.",
            "anchor": "",
            "source": "",
            "is_negative": True
        })

    with open(OUTPUT_SET, "w", encoding="utf-8") as f:
        json.dump(golden_set, f, ensure_ascii=False, indent=2)

    print(f"Golden Set создан! Всего вопросов: {len(golden_set)} (включая {len(negative_questions)} негативных)")

if __name__ == "__main__":
    build_golden_set(sample_size=95)

"""День 38: сбор ответов agentic RAG и оценка RAGAS (см. README.md)."""

import argparse
import csv
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("faithfulness", "answer_relevancy", "context_precision",
           "context_recall", "answer_correctness")


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False), encoding="utf-8")


def extract_contexts(history):
    """Только реальные search outputs; порядок и повторы сохраняются."""
    searches = {item["call_id"] for item in history
                if item.get("type") == "function_call"
                and item.get("name") in ("search_documents", "search_in_document")}
    contexts, errors = [], []
    for item in history:
        if item.get("type") != "function_call_output":
            continue
        payload = json.loads(item["output"])
        if payload.get("error"):
            errors.append(payload["error"])
        if item.get("call_id") in searches:
            contexts.extend(hit["text"] for hit in payload.get("hits", [])
                            if hit.get("text"))
    return contexts, errors


def collect(args, out):
    cases = read_jsonl(args.dataset)
    if args.limit:
        cases = cases[:args.limit]
    if not cases or any(not isinstance(c.get("question"), str)
                        or not c["question"].strip() for c in cases):
        raise ValueError("Нужен непустой набор с полем question в каждой строке")
    chunks = Path(args.chunks).resolve()
    if not chunks.is_file():
        raise FileNotFoundError(chunks)
    # День 35 использует пути относительно корня проекта и глобальные настройки.
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    from Day35 import project_week_5 as agent
    from Day28 import project_week_4 as retrieval

    # Проверка до платных вызовов; коллекцию не создаём и не перезаписываем.
    if not retrieval.client.collection_exists(args.collection):
        raise ValueError(f"Нет коллекции Qdrant: {args.collection}")
    info = retrieval.client.get_collection(args.collection)
    if not {"dense", "sparse"} <= set(info.config.params.vectors or {}) | set(
            info.config.params.sparse_vectors or {}):
        raise ValueError("Нужна hybrid-коллекция с векторами dense и sparse")
    agent.COLLECTION = args.collection
    agent.MODEL = args.model
    agent.catalog = agent.Catalog(chunks)
    agent.DOC_LIST = "\n".join(f"- {d}" for d in agent.catalog.doc_ids())
    prompt = agent.history[0]["content"]
    agent.history[0]["content"] = prompt.split(
        "Available documents (doc_id — file):", 1)[0] + (
        "Available documents (doc_id — file):\n" + agent.DOC_LIST)
    write_json(out / "config.json", {
        "dataset": str(Path(args.dataset).resolve()), "collection": args.collection,
        "chunks": str(chunks), "model": args.model, "limit": args.limit,
        "context_chars_per_hit": 800,
    })
    with (out / "runs.jsonl").open("w", encoding="utf-8") as log:
        for i, case in enumerate(cases):
            print(f"[{i + 1}/{len(cases)}] {case['question']}")
            agent.reset_history()
            start = time.monotonic()
            answer, calls = agent.call_client(case["question"])
            contexts, errors = extract_contexts(agent.history)
            row = {
                "case_id": i, "question": case["question"],
                "reference": case.get("golden_answer") or None,
                "response": answer.answer if answer is not None else None,
                "retrieved_contexts": contexts, "tool_calls": calls,
                "tool_errors": errors, "error": "no_answer" if answer is None else None,
                "elapsed_seconds": round(time.monotonic() - start, 2),
                "structured_answer": answer.model_dump(mode="json") if answer else None,
            }
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            log.flush()


def finite(value):
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def summarize(rows):
    result = {"total": len(rows), "answered": sum(r.get("response") is not None
                                                 for r in rows), "metrics": {}}
    for name in METRICS:
        scores = [r[name] for r in rows if r.get(name) is not None]
        result["metrics"][name] = {
            "mean": sum(scores) / len(scores) if scores else None,
            "scored": len(scores), "missing": len(rows) - len(scores),
        }
    return result


def evaluate_runs(args, out):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (Faithfulness, ResponseRelevancy, LLMContextPrecisionWithReference,
                               LLMContextRecall, AnswerCorrectness)
    from ragas.run_config import RunConfig

    rows = read_jsonl(args.runs or out / "runs.jsonl")
    for row in rows:
        row.update({name: None for name in METRICS})
    llm = LangchainLLMWrapper(ChatOpenAI(model=args.judge_model, temperature=0))
    embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings(model=args.embedding_model))
    # Отдельный набор для reference-метрик: отсутствие эталона не маскируется пустой строкой.
    groups = [([r for r in rows if r.get("response") is not None],
               [Faithfulness(), ResponseRelevancy()]),
              ([r for r in rows if r.get("response") is not None and r.get("reference")],
               [LLMContextPrecisionWithReference(), LLMContextRecall(), AnswerCorrectness()])]
    for selected, metrics in groups:
        if not selected:
            continue
        dataset = EvaluationDataset.from_list([
            {"user_input": r["question"], "response": r["response"],
             "retrieved_contexts": r["retrieved_contexts"], "reference": r.get("reference")}
            for r in selected])
        result = evaluate(dataset, metrics=metrics, llm=llm, embeddings=embeddings,
                          run_config=RunConfig(timeout=180, max_workers=2),
                          raise_exceptions=False)
        for row, scores in zip(selected, result.scores):
            for name, value in scores.items():
                row[name] = finite(value)
    with (out / "scores.jsonl").open("w", encoding="utf-8") as log:
        for row in rows:
            log.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    with (out / "scores.csv").open("w", encoding="utf-8-sig", newline="") as log:
        writer = csv.DictWriter(log, fieldnames=["case_id", "question", "error", *METRICS],
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    summary = summarize(rows)
    summary.update(judge_model=args.judge_model, embedding_model=args.embedding_model)
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def compare(args, out):
    before = read_jsonl(Path(args.baseline) / "scores.jsonl")
    after = read_jsonl(Path(args.variant) / "scores.jsonl")
    left = {r["case_id"]: r for r in before}
    right = {r["case_id"]: r for r in after}
    if len(left) != len(before) or len(right) != len(after) or left.keys() != right.keys():
        raise ValueError("Наборы должны содержать одинаковые уникальные case_id")
    if any(left[i]["question"] != right[i]["question"] or
           left[i].get("reference") != right[i].get("reference") for i in left):
        raise ValueError("Вопросы и эталоны двух прогонов должны совпадать")
    for file in ("config.json", "summary.json"):
        a = json.loads((Path(args.baseline) / file).read_text(encoding="utf-8"))
        b = json.loads((Path(args.variant) / file).read_text(encoding="utf-8"))
        keys = ("model", "context_chars_per_hit") if file == "config.json" else (
            "judge_model", "embedding_model")
        if any(a.get(k) != b.get(k) for k in keys):
            raise ValueError(f"Несопоставимые настройки: {file}")
    delta = {}
    for name in METRICS:
        pairs = [(left[i][name], right[i][name]) for i in left
                 if left[i].get(name) is not None and right[i].get(name) is not None]
        delta[name] = {
            "paired_cases": len(pairs),
            "baseline": sum(a for a, b in pairs) / len(pairs) if pairs else None,
            "variant": sum(b for a, b in pairs) / len(pairs) if pairs else None,
            "delta": sum(b - a for a, b in pairs) / len(pairs) if pairs else None,
        }
    write_json(out / "delta.json", delta)
    print(json.dumps(delta, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", "collect", "evaluate", "compare"), default="all")
    parser.add_argument("--dataset", type=Path, default=ROOT / "Day37/out_data/eval_set_draft.jsonl")
    parser.add_argument("--collection", default="week_4_project")
    parser.add_argument("--chunks", type=Path, default=ROOT / "Day28/data/chunks_512.jsonl")
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--judge-model", default="gpt-4.1-mini")
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", type=Path, default=ROOT / "Day38/out_data/baseline_512")
    parser.add_argument("--runs", type=Path, help="Сохранённый runs.jsonl для отдельной оценки")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--variant", type=Path)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit должен быть положительным")
    if args.stage == "compare" and (not args.baseline or not args.variant):
        parser.error("compare требует --baseline и --variant")
    # Приводим пути к абсолютным до смены cwd в collect.
    for name in ("dataset", "chunks", "out", "runs", "baseline", "variant"):
        value = getattr(args, name)
        if value is not None:
            setattr(args, name, value.resolve())
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    if args.stage in ("all", "collect"):
        if (out / "runs.jsonl").exists():
            parser.error("runs.jsonl уже существует: выбери новый --out")
        collect(args, out)
    if args.stage in ("all", "evaluate"):
        evaluate_runs(args, out)
    if args.stage == "compare":
        compare(args, out)


if __name__ == "__main__":
    main()

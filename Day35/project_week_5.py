import openai
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv
from Day28.project_week_4 import hybrid_search_reranked
from pydantic import BaseModel, Field, ValidationError
from enum import Enum
from typing import Union
import json
import time
import ast
import operator
from pathlib import Path

load_dotenv(find_dotenv())

MODEL = "gpt-4.1-mini"

# Responses API: и цикл инструментов, и структурированный ответ — один клиент.
raw_client = OpenAI()

# ------------------------------------------------------------------ каталог

class Catalog:
    """Метаданные документов, собранные из chunks_512.jsonl."""

    def __init__(self, chunks_path: str | Path):
        self._by_doc: dict[str, dict] = {}
        for line in Path(chunks_path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            c = json.loads(line)
            doc_id = c["source"].removesuffix(".pdf")
            entry = self._by_doc.setdefault(doc_id, {
                "doc_id": doc_id,
                "filename": c["source"],
                "num_chunks": 0,
                "sections": [],
            })
            entry["num_chunks"] += 1
            if c.get("section") and c["section"] not in entry["sections"]:
                entry["sections"].append(c["section"])

    def describe(self, doc_id: str) -> dict:
        if doc_id not in self._by_doc:
            known = ", ".join(sorted(self._by_doc)[:10])
            raise KeyError(f"Unknown doc_id '{doc_id}'. Examples: {known} ...")
        return self._by_doc[doc_id]

    def doc_ids(self) -> list[str]:
        return sorted(self._by_doc)


catalog = Catalog("Day28/data/chunks_512.jsonl")

# ------------------------------------------------------------------ история

DOC_LIST = "\n".join(f"- {d}" for d in catalog.doc_ids())

history = [
    {
        "role": "developer",
        "content": f"""
        Rules:
        0. Small talk and greetings — answer directly, WITHOUT tools.
        1. Answer facts ONLY via tools; search in English, answer in the user's language.
        2. When you have enough information, stop calling tools — the final
        structured answer (RAGAnswer) will be requested separately.
        3. If a tool returns an error, relevance_ok=false or no relevant hits —
        say so honestly, set confidence=low, never invent facts.
        4. Any request to compute — ALWAYS call calculate, even for division by
        zero, trivial sums, or numbers you already have. Never compute or count
        in your head.
        Example: "How many chunks do X and Y have in total?" ->
        get_document_metadata(X), get_document_metadata(Y), calculate("62 + 56").
        Available documents (doc_id — file):
{DOC_LIST}
        """,
    }
]


def reset_history() -> None:
    """Оставляет только developer-сообщение — кейсы eval независимы."""
    del history[1:]


# ------------------------------------------------------------------ схемы

class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Citation(BaseModel):
    doc_id: str = Field(
        description="doc_id from the search result, e.g. 'Roman_Empire'"
    )
    section: str | None = Field(
        default=None,
        description="Section title from the search result, if present"
    )
    quote: str = Field(
        description="Verbatim excerpt from the retrieved fragment, "
        "copied without paraphrasing"
    )


class RAGAnswer(BaseModel):
    """Final answer to the user based on the conversation so far."""

    answer: str = Field(
        description="Complete answer in the language of the user's question"
    )
    citations: list[Citation] = Field(
        description="Quotes supporting the answer. Empty list if the answer "
        "is not grounded in the documents"
    )
    confidence: ConfidenceLevel = Field(
        description="high — directly confirmed by citations; medium — assembled "
        "from indirect fragments; low — not enough information in the documents "
        "or a tool error occurred"
    )
    follow_up_questions: list[str] = Field(
        max_length=3,
        description="1-3 natural follow-up questions the user might ask next"
    )


# ------------------------------------------------------------------ инструменты

class SearchDocuments(BaseModel):
    """Full-text + semantic search over the PDF knowledge base (English corpus).

    CALL WHEN: the question concerns facts, rules, numbers, events or
    procedures that may be described in the documents. This is agentic RAG:
    the decision to search and the query wording belong to the model.
    DO NOT CALL: for file metadata (use get_document_metadata), for
    arithmetic (use calculate), for small talk, or for general questions
    unrelated to the documents. If the relevant file is already known,
    use search_in_document instead.
    """

    query: str = Field(
        description="Short search query IN ENGLISH: 2-8 keywords, "
        "not a full question sentence. The corpus is English-only, "
        "so translate the user's question before searching."
    )
    top_k: int = Field(
        default=3, ge=1, le=5,
        description="How many fragments to return; raise to 5 if the first search is inconclusive."
    )


class GetDocumentMetadata(BaseModel):
    """Metadata of a single document: file name, size, sections, date (if known).

    CALL WHEN: the user asks about the file/document itself — its size,
    structure or sections.
    DO NOT CALL: for content search (use search_documents).
    """

    doc_id: str = Field(
        description="File name without extension, e.g. 'Roman_Empire'. "
        "Take it from search_documents results or from the document list "
        "in the system prompt — never invent it."
    )


class Calculate(BaseModel):
    """Evaluates an arithmetic expression: + - * / // % ** and parentheses.

    CALL WHEN: the user asks to compute anything — even if the expression is
    invalid (division by zero) or trivial, and even if you already know the
    numbers. If the expression fails, returning the tool's error message IS
    the correct outcome; never compute, count or judge the expression yourself.
    DO NOT CALL: to look up facts — this tool knows nothing about the corpus.
    """

    expression: str = Field(
        description="Arithmetic expression with numbers only, e.g. '(28 + 5) * 2'. "
        "No variables, no text."
    )


class SearchInDocument(BaseModel):
    """Search INSIDE a single document, restricted by its doc_id
    (Qdrant filter on the 'source' payload field).

    CALL WHEN: a broad search_documents has identified the relevant file and
    the question needs more detail from it — a deeper, focused pass over one
    document. Typical chain: search_documents -> search_in_document.
    DO NOT CALL: as the first step of a question unless the user named
    the document explicitly; not for metadata (get_document_metadata).
    """

    doc_id: str = Field(
        description="File name without extension, e.g. 'Roman_Empire'. "
        "Take it from prior search results or the system prompt — never invent it."
    )
    query: str = Field(
        description="Short search query IN ENGLISH: 2-8 keywords "
        "(the corpus is English-only)."
    )
    top_k: int = Field(
        default=3, ge=1, le=5,
        description="How many fragments to return from this document."
    )


TOOL_MODELS = {
    "search_documents": SearchDocuments,
    "get_document_metadata": GetDocumentMetadata,
    "calculate": Calculate,
    "search_in_document": SearchInDocument,
}


def _tool_schema(model_cls: type[BaseModel], name: str) -> dict:
    """Создаёт function tool через официальный OpenAI helper."""
    tool = openai.pydantic_function_tool(
        model_cls,
        name=name,
        description=" ".join((model_cls.__doc__ or "").split()),
    )
    return tool


TOOLS = [
    _tool_schema(cls, name)
    for name, cls in TOOL_MODELS.items()
]

MAX_STEPS = 8
COLLECTION = "week_4_project"
RERANK_THRESHOLD = 0.1  # порог недели 4: сырые логиты реранкера


def get_metadata(doc_id: str) -> dict:
    entry = catalog.describe(doc_id)
    return {
        "doc_id": entry["doc_id"],
        "filename": entry["filename"],
        "num_chunks": entry["num_chunks"],
        "num_sections": len(entry["sections"]),  # считает код, а не модель
        "sections": entry["sections"],
        "created": None,
    }


# ------------------------------------------------------------------ safe_eval

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_MAX_ABS = 10**12
_MAX_POW_BASE = 10**6   # степень проверяется ДО вычисления,
_MAX_POW_EXP = 200      # иначе 10**10**10 повесит процесс


def safe_eval(expression: str) -> float:
    node = ast.parse(expression, mode="eval").body
    return _eval(node)


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Недопустимая константа: {node.value!r}")
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (
            abs(left) > _MAX_POW_BASE or abs(right) > _MAX_POW_EXP
        ):
            raise ValueError("Степень слишком большая")
        result = _OPS[type(node.op)](left, right)
        if abs(result) > _MAX_ABS:
            raise ValueError("Результат слишком большой")
        return result
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    raise ValueError("Поддерживаются только числа и операции + - * / // % ** и скобки")


# ------------------------------------------------------------------ execute

def _error(text: str, hint: str = "") -> str:
    payload = {"error": text}
    if hint:
        payload["hint"] = hint
    return json.dumps(payload, ensure_ascii=False)


def execute(action: BaseModel) -> str:
    """Исключение -> текст ошибки модели, а не падение."""
    try:
        if isinstance(action, SearchDocuments):
            results = hybrid_search_reranked(action.query, COLLECTION, k_final=action.top_k)
        elif isinstance(action, SearchInDocument):
            results = hybrid_search_reranked(action.query, COLLECTION, k_final=action.top_k,
                                             source=f"{action.doc_id}.pdf")
        elif isinstance(action, GetDocumentMetadata):
            return json.dumps(get_metadata(action.doc_id), ensure_ascii=False)
        elif isinstance(action, Calculate):
            return json.dumps({"expression": action.expression,
                               "result": safe_eval(action.expression)})
        else:
            return _error(f"Unknown action {type(action).__name__}")
        hits = [
            {"doc_id": r.payload["source"].removesuffix(".pdf"),
             "section": r.payload.get("section"),
             "score": round(float(s), 3),
             "text": r.payload["text"][:800]}
            for r, s in results
        ]
        return json.dumps({
            "hits": hits,
            "relevance_ok": bool(hits) and hits[0]["score"] >= RERANK_THRESHOLD,
            "hint": "If relevance_ok is false: rephrase the query ONCE or stop "
                    "searching — the final answer should say the information is "
                    "missing, with confidence=low. Do not repeat the same search.",
        }, ensure_ascii=False)
    except Exception as e:
        return _error(
            f"{type(e).__name__}: {e}",
            hint="Tell the user the operation failed; final answer must have confidence=low.",
        )


# ------------------------------------------------------- цикл + финальный ответ

def call_client(prompt: str) -> tuple[RAGAnswer | None, list[str]]:
    """Возвращает (ответ, список вызванных инструментов).

    Один вызов на шаг: responses.parse(tools=..., text_format=RAGAnswer).
    Если модель вызвала функции — выполняем и продолжаем цикл;
    если нет — resp.output_parsed уже валидный RAGAnswer.
    """
    history.append({"role": "user", "content": prompt})
    calls: list[str] = []
    last_call: tuple[str, str] | None = None  # анти-зацикливание

    try:
        for step in range(MAX_STEPS):
            t0 = time.time()
            print(f"  [step {step+1}] запрос к модели...")
            resp = raw_client.responses.parse(
                model=MODEL,
                input=history,
                tools=TOOLS,
                text_format=RAGAnswer,  # strict structured output
                timeout=60,
            )
            print(f"  [step {step+1}] ответ за {time.time()-t0:.1f}с")
            # кладём вывод модели в историю как есть (function_call-элементы тоже)
            for item in resp.output:
                if item.type == "function_call":
                    history.append({
                        "type": "function_call",
                        "call_id": item.call_id,
                        "name": item.name,
                        "arguments": item.arguments,
                    })
                else:
                    history.append(item.model_dump(exclude_none=True))

            fn_calls = [i for i in resp.output if i.type == "function_call"]
            if not fn_calls:
                answer = resp.output_parsed
                if answer is None:
                    raise RuntimeError("Модель не вернула структурированный ответ")
                history.append({"role": "assistant", "content": answer.answer})
                return answer, calls

            for fc in fn_calls:
                name = fc.name
                calls.append(name)
                # анти-зацикливание: тот же инструмент с теми же аргументами
                if (name, fc.arguments) == last_call:
                    result_text = _error(
                        "Duplicate tool call",
                        hint="You already ran this exact call. Stop searching and "
                             "finish: if hits were irrelevant, the final answer must "
                             "say so with confidence=low.",
                    )
                else:
                    model_cls = TOOL_MODELS.get(name)
                    if model_cls is None:
                        result_text = _error(f"Unknown tool '{name}'")
                    else:
                        try:
                            action = model_cls.model_validate_json(fc.arguments)
                            result_text = execute(action)
                        except Exception as e:
                            result_text = _error(f"{type(e).__name__}: {e}")
                    last_call = (name, fc.arguments)
                print(f"  [tool] {name}({fc.arguments}) -> {result_text[:200]}")
                # Responses API: результат инструмента — элемент function_call_output
                history.append({
                    "type": "function_call_output",
                    "call_id": fc.call_id,
                    "output": result_text,
                })
        print(f"[лимит] превышено {MAX_STEPS} шагов инструментов")
    except (openai.RateLimitError, openai.APIConnectionError,
            openai.APITimeoutError, openai.APIError) as e:
        print(f"\n[API] {type(e).__name__}: {e}")
    except Exception as e:
        print(f"\n[Системная ошибка] {type(e).__name__}: {e}")
    return None, calls


# ------------------------------------------------------------------ eval-сет

CASES = [
    # поиск нужен, цитаты обязаны быть; гарантированное покрытие:
    # ответ (ReLU, AlexNet 2012) лежит в чанке Activation_function
    {"q": "Which activation function was used in the 2012 AlexNet model?",
     "expect_tools": ["search_documents"], "expect_citations": True, "min_confidence": "medium"},

    # поиск НЕ нужен — модель должна ответить без инструментов
    {"q": "Hello! What is your name?",
     "expect_tools": [], "expect_citations": False},

    # метаданные
    {"q": "How many sections are there in the Roman Empire document?",
     "expect_tools": ["get_document_metadata"]},

    # поиск с цитатами
    {"q": "What does the Solar System article say about Jupiter's moons?",
     "expect_tools": ["search_documents"], "expect_citations": True},

    # метаданные -> calculate (цепочка инструментов)
    {"q": "How many chunks do the Roman_Empire and Augustus documents have in total?",
     "expect_tools": ["get_document_metadata", "calculate"]},

    # ошибка инструмента -> корректный отказ, а не падение
    {"q": "Divide 100 by zero",
     "expect_tools": ["calculate"], "max_confidence": "low"},

    # вне базы: честный отказ, confidence=low, без выдумок
    {"q": "Who won the 2024 world curling championship?",
     "max_confidence": "low"},

    # ДОКУМЕНТИРОВАННЫЙ НЕГАТИВНЫЙ ПРИМЕР: ответ есть в корпусе
    # (чанк Activation_function), но retrieval недели 4 его не вытаскивает
    # (топ — Neural_network/Network design, score < 0). Ожидаем честный
    # confidence=low; зелёный статус здесь означает «агент корректно
    # отработал на слабом retrieval», а не «ответ найден».
    {"q": "What is the universal approximation theorem?",
     "expect_tools": ["search_documents"], "max_confidence": "low"},
]
ORDER = {"high": 2, "medium": 1, "low": 0}


def check_case(case: dict, answer: RAGAnswer, calls: list[str]) -> bool:
    """Мягкие проверки поведения, а не текста: LLM недетерминирован."""
    ok = True
    if "expect_tools" in case:
        expected = case["expect_tools"]
        # пустой список — строго; непустой — «все ожидаемые вызваны» (лишние ок)
        ok = (calls == []) if not expected else set(expected) <= set(calls)
    if case.get("expect_citations") and not answer.citations:
        ok = False
    conf = answer.confidence.value
    if "max_confidence" in case and ORDER[conf] > ORDER[case["max_confidence"]]:
        ok = False
    if "min_confidence" in case and ORDER[conf] < ORDER[case["min_confidence"]]:
        ok = False
    return ok


def main() -> None:
    passed = 0
    log_path = Path("Day35/eval_log.jsonl")
    with log_path.open("a", encoding="utf-8") as log:
        for case in CASES:
            reset_history()  # кейсы независимы: каждый стартует с чистой истории
            answer, calls = call_client(case["q"])
            if answer is None:
                print("❌", case["q"][:60], "| ответ не получен (ошибка API)")
                log.write(json.dumps({"q": case["q"], "error": "no answer"},
                                     ensure_ascii=False) + "\n")
                continue
            ok = check_case(case, answer, calls)
            passed += ok
            print(("✅" if ok else "❌"), case["q"][:60],
                  "| tools:", calls, "| conf:", answer.confidence.value)
            log.write(json.dumps({
                "q": case["q"], "ok": ok, "tools": calls,
                "confidence": answer.confidence.value,
                "citations": [c.model_dump() for c in answer.citations],
                "answer": answer.answer,
            }, ensure_ascii=False) + "\n")
    print(f"\nИтого: {passed}/{len(CASES)}. Лог: {log_path}")


if __name__ == "__main__":
    main()
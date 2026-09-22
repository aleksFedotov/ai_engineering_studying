import hashlib
import json
import re
from pathlib import Path
from tqdm import tqdm
import time

from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer
from rapidfuzz import fuzz

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "wiki_pdfs"
OUTPUT_DIR = BASE_DIR / "data"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DROP_SECTIONS = {
    "references", "see also", "external links", "notes",
    "further reading", "bibliography", "citations","books", 
    "journals", "modern sources", "notes and references",
    "primary sources", "sources", "general references"
}

# ---------- 1. Чанкинг ----------

def make_tokenizer(max_tokens: int) -> HuggingFaceTokenizer:
    return HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained("intfloat/e5-base-v2"),
        max_tokens=max_tokens,
    )

def make_chunker(tokenizer: HuggingFaceTokenizer) -> HybridChunker:
    return HybridChunker(tokenizer=tokenizer, merge_peers=True)


def merge_small_chunks(chunks: list[dict], tokenizer, max_tokens: int) -> list[dict]:
    merged, buf, buf_ids = [], None, []
    def flush():
        nonlocal buf, buf_ids
        if buf:
            buf["merged_from"] = buf_ids
            merged.append(buf)
        buf, buf_ids = None, []
    for c in chunks:
        if buf is None:
            buf, buf_ids = dict(c), [c["id"]]
            continue
        candidate = buf["text"] + "\n" + c["text"]
        same_doc = buf["source"] == c["source"]
        fits = len(tokenizer.tokenizer.encode(candidate)) <= max_tokens
        if same_doc and fits:
            buf["text"] = candidate
            buf_ids.append(c["id"])
        else:
            flush()
            buf, buf_ids = dict(c), [c["id"]]
    flush()

    counters = {}
    for m in merged:
        idx = counters.get(m["source"], 0)
        m["chunk_index"] = idx
        m["id"] = f"{Path(m['source']).stem}_chunk_{idx}"
        counters[m["source"]] = idx + 1
    return merged

def is_garbage(text: str) -> bool:
    letters = sum(ch.isalpha() for ch in text)
    return letters / max(len(text), 1) < 0.55 or text.count("= .") >= 3

def chunk_document(document, source_name: str, chunker) -> list[dict]:
    chunks, idx = [], 0
    for item in chunker.chunk(document):
        headings = [h.strip().lower() for h in (item.meta.headings or [])]
        if any(h in DROP_SECTIONS for h in headings):
            continue
        text = chunker.contextualize(item)
        if len(text.split()) < 15:       
            continue
        if is_garbage(text):              
            tqdm.write(f"  мусор отфильтрован: {source_name} / {item.meta.headings}")
            continue
        chunks.append({
            "source": source_name,
            "section": " / ".join(item.meta.headings or []),
            "text": text,
            "chunk_index": idx,
            "id": f"{Path(source_name).stem}_chunk_{idx}",
        })
        idx += 1
    return chunks

# ---------- 2. Дедупликация ----------

def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()

def dedup_exact(chunks: list[dict]) -> list[dict]:
    seen, unique = {}, []
    for c in chunks:
        h = hashlib.md5(normalize(c["text"]).encode()).hexdigest()
        if h in seen:
            tqdm.write(f"  дубль удалён: {c['id']} == {seen[h]}")
            continue
        seen[h] = c["id"]
        unique.append(c)
    return unique

def report_near_dups(chunks: list[dict], threshold: int = 90) -> list[tuple]:
    texts = [(c["id"], normalize(c["text"])) for c in chunks]
    pairs = []
    for i in tqdm(range(len(texts)), desc="Поиск near-дублей", unit="чанк"):
        for j in range(i + 1, len(texts)):
            score = fuzz.ratio(texts[i][1], texts[j][1])
            if score >= threshold:
                pairs.append((texts[i][0], texts[j][0], score))
    return pairs

# ---------- 3. Пайплайн ----------

def prepare_corpus(max_tokens: int = 512) -> list[dict]:
    converter = DocumentConverter()
    tokenizer = make_tokenizer(max_tokens)
    chunker = make_chunker(tokenizer)

    pdf_files = sorted(DOCS_DIR.glob("*.pdf"))
    all_chunks = []


    for pdf in tqdm(pdf_files, desc="Парсинг PDF", unit="файл"):
        t0 = time.time()
        r = converter.convert(pdf)
        chunks = chunk_document(r.document, pdf.name, chunker)
        chunks = merge_small_chunks(chunks, tokenizer, max_tokens)
        all_chunks.extend(chunks)
        tqdm.write(f"  {pdf.name}: {len(chunks)} чанков за {time.time() - t0:.1f} сек")
    print(f"После чанкинга: {len(all_chunks)}")

    all_chunks = dedup_exact(all_chunks)         
    print(f"После дедупликации: {len(all_chunks)}")

    near = report_near_dups(all_chunks)
    print(f"Near-дублей (>90%): {len(near)} — НЕ удаляем, кандидаты в golden-set")
    for a, b, s in near[:20]:
        print(f"  {s:.0f}%: {a} ~ {b}")

    out = OUTPUT_DIR / f"chunks_{max_tokens}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Сохранено в {out}")
    return all_chunks

if __name__ == "__main__":
    prepare_corpus(max_tokens=512)
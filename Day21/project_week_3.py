from langchain_text_splitters import RecursiveCharacterTextSplitter
import tiktoken  
from docling.document_converter import DocumentConverter
from pathlib import Path
import json

import argparse
from sentence_transformers import SentenceTransformer

converter = DocumentConverter()

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
OUTPUT_DIR  = BASE_DIR /  'OUTPUT'

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def make_splitter(size: int, overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=size,
        chunk_overlap=overlap,
    )

def extract_pages(document) -> dict[int, str]:
    """Возвращает {номер_страницы: текст страницы}"""
    pages = {}
    for item, _level in document.iterate_items():
        text = getattr(item, "text", None)
        if not text or not item.prov:
            continue
        page_no = item.prov[0].page_no          
        pages.setdefault(page_no, []).append(text)
    return {p: "\n".join(texts) for p, texts in pages.items()}

def chunk_pdf(document, source_name: str, splitter:RecursiveCharacterTextSplitter ) -> list[dict]:
    pages = extract_pages(document)
    chunks = []
    for page_no in sorted(pages):
        for chunk_text in splitter.split_text(pages[page_no]):
            chunks.append({
                "source": source_name,
                "page": page_no,
                "text": chunk_text,
            })
    return chunks

def build_chunks(splitter:RecursiveCharacterTextSplitter ) -> list[dict]:
    all_chunks = []

    # PDF — с реальными страницами
    pdf_files = sorted(DOCS_DIR.glob("*.pdf"))
    results = converter.convert_all(pdf_files, raises_on_error=False)
    for r in results:
        if r.status.name != "SUCCESS":
            print(f" Ошибка при обработке: {r.input.file.name}")
            continue
        source = r.input.file.name                     # исходное имя, с .pdf
        all_chunks.extend(chunk_pdf(r.document, source, splitter))
        print(f" Готово: {source}")

    # Markdown — страницы нет, ставим None
    for md_path in sorted(DOCS_DIR.glob("*.md")):
        for chunk_text in splitter.split_text(md_path.read_text(encoding="utf-8")):
            all_chunks.append({
                "source": md_path.name,
                "page": None,
                "text": chunk_text,
            })

    # общая нумерация чанков внутри каждого файла
    counters = {}
    for c in all_chunks:
        idx = counters.get(c["source"], 0)
        c["chunk_index"] = idx
        c["id"] = f"{Path(c['source']).stem}_chunk_{idx}"  
        counters[c["source"]] = idx + 1

    return all_chunks

def save_json(chunks : list[dict]):
    jsonl_output_path = OUTPUT_DIR / "chunks.jsonl"
    with open(jsonl_output_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f" Успешно сохранено {len(chunks)} чанков в {jsonl_output_path.name}")


def embedding(model_name: str):
    model = SentenceTransformer(model_name)


    chunks = []
    with open(OUTPUT_DIR / "chunks.jsonl", encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))

    if "e5" in model_name and not model.prompts:
        texts = ["passage: " + c["text"] for c in chunks]
    else:
        texts = [c["text"] for c in chunks]
    vectors = model.encode(texts, batch_size=32, show_progress_bar=True)
    with open(OUTPUT_DIR / "index.jsonl", "w", encoding="utf-8") as f:
        for chunk, vec in zip(chunks, vectors):
            chunk["vector"] = vec.tolist()   
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

def visualize(index_path=OUTPUT_DIR / "index.jsonl"):
    import umap
    import numpy as np
    import matplotlib.pyplot as plt

    # 1. Читаем индекс
    chunks = []
    with open(index_path, encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))

    vectors = np.array([c["vector"] for c in chunks])
    sources = [c["source"] for c in chunks]

    
    reducer = umap.UMAP(
        n_neighbors=min(5, len(chunks) - 1),   # см. разбор ниже
        min_dist=0.1,
        metric="cosine",                       # важно: наша метрика!
        random_state=42,                       # воспроизводимость
    )
    points = reducer.fit_transform(vectors)    # shape: (N, 2)

  
    plt.figure(figsize=(10, 7))
    unique_sources = sorted(set(sources))
    for src in unique_sources:
        mask = [s == src for s in sources]
        plt.scatter(points[mask, 0], points[mask, 1], label=src, alpha=0.8)

    plt.legend(fontsize=8, markerscale=1.5)
    plt.title("UMAP-проекция чанков (цвет = документ)")
    out_path = OUTPUT_DIR / "umap_chunks.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f" Картинка сохранена: {out_path.name}")

def main():
    parser = argparse.ArgumentParser(description="CLI EMBEDDING")


    parser.add_argument(
        "--model",
        choices =[
        "intfloat/multilingual-e5-small",               # 118M, быстрая, дефолт
        "intfloat/multilingual-e5-base",                # 278M, заметно точнее
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",  # классика, 118M
    ],
        default="intfloat/multilingual-e5-small",
        help="Выбор модели"
    )

    parser.add_argument(
        "--chunk_size",
        type=int,
        default=512,
        help="Размер chunk"
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=80,
        help="Размер overlap"
    )

    parser.add_argument(
        "--visualize",
        action="store_true",          
        help="Построить UMAP-проекцию чанков"
    )

    
    args = parser.parse_args()
    model_name = args.model
    chunk_size  = args.chunk_size
    overlap  = args.overlap

    splitter = make_splitter(chunk_size, overlap)

    chunks = build_chunks(splitter)
    save_json(chunks)
    embedding(model_name)

    if args.visualize:
        visualize()



if __name__ == "__main__":
    main()
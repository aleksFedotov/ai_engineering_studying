from langchain_text_splitters import RecursiveCharacterTextSplitter
import tiktoken  
from docling.document_converter import DocumentConverter
from pathlib import Path
import json


encoder = tiktoken.get_encoding('cl100k_base')
converter = DocumentConverter()



BASE_DIR = Path(__file__).resolve().parent
PDF_DIR = BASE_DIR / "PDF"
MARKDOWN_DIR = BASE_DIR / "MARKDOWN"
OUTPUT_DIR = BASE_DIR / "OUTPUT"

MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

pdf_files = list(PDF_DIR.glob("*.pdf"))


def recursive_chunking(text:str, size : int = 500, overlap: int = 100) -> list[str]:
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base", 
        chunk_size=size,
        chunk_overlap=overlap
    )



    return text_splitter.split_text(text)

if not pdf_files:
    print(f"В директории {PDF_DIR} не найдено ни одного PDF файла.")
else:
    print(f"Найдено файлов для обработки: {len(pdf_files)}")

    results = converter.convert_all(pdf_files,raises_on_error=False)

    for result in results:
        if result.status.name == "SUCCESS" or getattr(result, "status", None) == "SUCCESS":
            file_stem = result.input.file.stem


            markdown_content = result.document.export_to_markdown()

            out_file = MARKDOWN_DIR / f"{file_stem}.md"

            out_file.write_text(markdown_content, encoding="utf-8")
            print(f" Готово: {file_stem}.md")
        else:
            print(f" Ошибка при обработке: {result.input.file.name}")
markdown_files = list(MARKDOWN_DIR.glob("*.md"))

all_chunks_data = []
if not markdown_files: 
    print(f"В директории {markdown_files} не найдено ни одного md файла.")
else:
    print(f"\nНайдено Markdown файлов: {len(markdown_files)}")
    
for md_path in markdown_files:
    content = md_path.read_text(encoding="utf-8")
    chunks = recursive_chunking(text=content, size=200, overlap=20)

    for idx, chunk_text in enumerate(chunks):
            chunk_id = f"{md_path.stem}_chunk_{idx}"
            all_chunks_data.append({
                "id": chunk_id,
                "source": md_path.name,
                "chunk_index": idx,
                "text": chunk_text,
                "tokens": len(encoder.encode(chunk_text))
            })


jsonl_output_path = OUTPUT_DIR / "chunks.jsonl"
with open(jsonl_output_path, "w", encoding="utf-8") as f:
    for chunk in all_chunks_data:
        f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

print(f" Успешно сохранено {len(all_chunks_data)} чанков в {jsonl_output_path.name}")


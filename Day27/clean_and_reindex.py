import json
from pathlib import Path
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


DROP_SECTIONS = {
    "references", "see also", "external links", "notes",
    "further reading", "bibliography", "citations", "books", 
    "journals", "modern sources", "notes and references",
    "primary sources", "sources", "general references",
    "other sources", "ancient sources", "secondary sources",
    "book chapters and encyclopaedias", "multimedia", "depictions"
}

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

def is_bad_section(section_str: str) -> bool:
    headings = [h.strip().lower() for h in section_str.split("/")]
    return any(h in DROP_SECTIONS for h in headings)

def clean_jsonl(file_name: str):
    path = DATA_DIR / file_name
    if not path.exists():
        return
    
    cleaned = []
    removed_count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            chunk = json.loads(line)
            if is_bad_section(chunk.get("section", "")):
                removed_count += 1
            else:
                cleaned.append(chunk)
                
    with open(path, "w", encoding="utf-8") as f:
        for chunk in cleaned:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            
    print(f"{file_name}: удалено {removed_count} мусорных чанков, осталось {len(cleaned)}")

if __name__ == "__main__":
    clean_jsonl("chunks_512.jsonl")
    clean_jsonl("chunks_256.jsonl")
    print("Файлы очищены. Запустите build_index.py для перезаписи коллекций в Qdrant.")
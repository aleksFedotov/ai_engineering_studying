
import json
import pandas as pd
from pathlib import Path
import re

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

def load_jsonl(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]

def relevant_pairs(item):
    """Список {source, anchor} независимо от схемы записи."""
    if "relevant" in item:
        return item["relevant"]
    if item.get("source") and item.get("anchor"):
        return [{"source": item["source"], "anchor": item["anchor"]}]
    return []

def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()

def map_anchors():
    golden_path = DATA_DIR / "golden_set.json"
    if not golden_path.exists():
        print("Golden set не найден!")
        return

    with open(golden_path, "r", encoding="utf-8") as f:
        golden_set = json.load(f)

    chunks_512 = load_jsonl(DATA_DIR / "chunks_512.jsonl")
    chunks_256 = load_jsonl(DATA_DIR / "chunks_256.jsonl")

    mapped_count = 0

    for item in golden_set:
        if item["is_negative"]:
            item["expected_ids_512"] = []
            item["expected_ids_256"] = []
            continue

        ids_512, ids_256 = [], []
        for rel in relevant_pairs(item):
            anchor = norm(rel["anchor"])
            source = rel["source"]
            ids_512 += [c["id"] for c in chunks_512
                        if c["source"] == source and anchor in norm(c["text"])]
            ids_256 += [c["id"] for c in chunks_256
                        if c["source"] == source and anchor in norm(c["text"])]

        # дедуп с сохранением порядка
        item["expected_ids_512"] = list(dict.fromkeys(ids_512))
        item["expected_ids_256"] = list(dict.fromkeys(ids_256))

        if item["expected_ids_512"] and item["expected_ids_256"]:
            mapped_count += 1
        else:
            print(f"⚠️ {item['id']}: 512={len(item['expected_ids_512'])}, 256={len(item['expected_ids_256'])}")

    # Сохраняем итоговые файлы
    output_json = DATA_DIR / "golden_set_mapped.json"
    output_csv = DATA_DIR / "golden_set_mapped.csv"

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(golden_set, f, ensure_ascii=False, indent=2)

    df = pd.DataFrame(golden_set)
    df.to_csv(output_csv, index=False)

    print(f"\nМаппинг завершен!")
    print(f"Успешно смапплено для обоих плеч: {mapped_count}/{len(golden_set) - 5}")
    print(f"Файлы сохранены в {output_json} и {output_csv}")

if __name__ == "__main__":
    map_anchors()
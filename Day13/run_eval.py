from project_2 import get_response, MODEL_MAP, PRICES, SummaryResults

from pathlib import Path
from datetime import datetime
import json

def quote_fidelity(result: SummaryResults, source_text: str) -> float:
    quotes = [kp.quote for kp in result.key_points] + [ai.quote for ai in result.action_items]
    if not quotes:
        return 0.0
    norm = lambda s: " ".join(s.split())  # 
    src = norm(source_text)
    return sum(1 for q in quotes if norm(q) in src) / len(quotes)

def print_pretty_summary(data: dict, model_type: str, test_case: str, cost: float,fidelity: float):
    result: SummaryResults = data["result"]
    
    
    key_points_count = len(result.key_points)
    actions_count = len(result.action_items)
    topics_count = len(result.topics)
    time_spent = data["elapsed_time"]
    
    print(f"{'Тест':<20} | {'Модель':<12} | {'Время':<8} | {'$':<10} | {'Тезисов':<7} | {'Действий':<8} | {'Тем':<4} | {'Fidelity':<8}")
    print("-" * 85)
    print(f"{test_case:<20} | {model_type:<12} | {time_spent:<7.2f}с | {cost:<10.6f} | {key_points_count:<7} | {actions_count:<8} | {topics_count:<4} | {fidelity:<8.2f}")
    print("\n")

def save_to_jsonl(data: dict, model_type: str, test_case: str, cost: float, fidelity: float, filepath: str = "eval_results.jsonl"):
    result: SummaryResults = data["result"]
    
   
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "test_case": test_case,
        "model_type": model_type,
        "metrics": {
            "elapsed_time": round(data["elapsed_time"], 3),
            "prompt_tokens": data["prompt_tokens"],
            "completion_tokens": data["completion_tokens"],
            "cost_usd": round(cost, 6),
            "quote_fidelity": round(fidelity, 3),
        },
        # Превращаем Pydantic-объект в dict для сериализации
        "data": result.model_dump()
    }
    
    # Записываем строкой в конец файла (a = append)
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        
    print(f"📁 Результат сохранен в {filepath}")


def main():
    folder_path = Path("./test_cases")
    summary = {}
    for model_type, model_name in MODEL_MAP.items():
        for file_path in folder_path.glob("*.txt"):
            if file_path.is_file():
                text = file_path.read_text(encoding="utf-8")
                result = get_response(model_name, text)
                if result is  None:
                    continue
                rates = PRICES[model_name]
                cost = (result["prompt_tokens"] * rates["input"]) + (result["completion_tokens"] * rates["output"])
                fidelity = quote_fidelity(result["result"], text)
                print_pretty_summary(result, model_name, file_path.name, cost,fidelity)
                save_to_jsonl(result, model_name, file_path.name, cost,fidelity)

                summary.setdefault(model_name, {"cost": [], "fidelity": []})
                summary[model_name]["cost"].append(cost)
                summary[model_name]["fidelity"].append(fidelity)

    
    print("=" * 60)
    print("ИТОГО: сравнение моделей")
    print(f"{'Модель':<12} | {'Ср. стоимость':<14} | {'Ср. fidelity':<12}")
    for model_name, m in summary.items():
        avg_cost = sum(m["cost"]) / len(m["cost"])
        avg_fid = sum(m["fidelity"]) / len(m["fidelity"])
        print(f"{model_name:<12} | ${avg_cost:<13.6f} | {avg_fid:<12.2f}")


if __name__ == "__main__":
    main()
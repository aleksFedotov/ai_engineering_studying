"""
evaluate.py — мини-оценка (evaluation) инструментов по мотивам источника №1 дня 32.

Что измеряем (метрики из статьи Anthropic):
  - точность выбора инструментов (tool selection accuracy)
  - корректность финального ответа (answer accuracy, простые проверки подстрок)
  - среднее число вызовов инструментов на задачу (эффективность стратегии)
  - ошибки инструментов (tool errors)

Как пользоваться:
  1. Положите рядом с вашим practise.py (нужны openai_tools, call_function, get_response).
  2. python evaluate.py            — прогон всего набора N_RUNS раз
  3. python evaluate.py --runs 5   — другое число повторов
  4. Результат печатается в консоль и сохраняется в eval_results.json

Для эксперимента «без WHEN NOT TO USE»: замените openai_tools на вариант
без этого блока (например, импортируйте другой список) — метрики посчитаются
так же, и сравнение будет честным (те же задачи, то же число прогонов).
"""

import argparse
import json
import time
from typing import Any

from practise import openai_tools, call_function, get_response, MAX_STEPS, BASE_DIR

# ---------------------------------------------------------------------------
# Оценочные задачи.
#   q             — формулировка задачи (как видит модель)
#   must_use      — инструменты, которые ДОЛЖНЫ быть вызваны (хотя бы раз)
#   must_not_use  — инструменты, которые НЕ должны вызываться
#   answer_any    — итоговый ответ считается верным, если содержит ЛЮБУЮ
#                   из этих подстрок (регистр не важен). Пустой список = не проверяем.
#   max_calls     — мягкий ориентир эффективности (не провал, только статистика)
# ---------------------------------------------------------------------------
TASKS = [
    {
        "q": "Сколько заказов у Анны и что она купила?",
        "must_use": ["get_customer_profile", "query_sql"],
        "must_not_use": [],
        "answer_any": ["клавиатур", "мыш", "монитор"],
        "max_calls": 3,
    },
    {
        "q": "Какие заказы у Ольги?",
        "must_use": ["query_sql"],
        "must_not_use": [],
        "answer_any": ["нет заказ", "не имеет заказ", "отсутствуют заказ"],
        "max_calls": 3,
    },
    {
        "q": "Сколько потратила Мария?",
        "must_use": ["query_sql"],
        "must_not_use": [],
        "answer_any": ["0", "не потратила", "не совершал"],
        "max_calls": 3,
    },
    {
        "q": "У кого больше заказов — у Анны или у Ивана?",
        "must_use": ["query_sql"],
        "must_not_use": [],
        "answer_any": ["у анны больше", "анны больше", "анна — 3", "анна: 3"],
        "max_calls": 4,
    },
    {
        "q": "Покажи заказы клиента, который купил наушники",
        "must_use": ["query_sql"],
        "must_not_use": ["get_customer_profile"],
        "answer_any": ["не найден", "нет заказ", "нет записей", "отсутствуют", "не обнаружен"],
        "max_calls": 2,
    },
    {
        "q": "Сколько всего оплат в таблице payments",
        "must_use": [],                       # правильно — НЕ вызывать инструменты
        "must_not_use": ["query_sql", "get_customer_profile"],
        "answer_any": ["нет таблиц", "таблицы", "не содержит таблиц", "customers", "orders"],
        "max_calls": 0,
    },
    # --- Приграничные задачи (граница между двумя инструментами) ---
    {
        "q": "Покажи профиль клиента с customer_id = 2",
        "must_use": ["query_sql"],            # у get_customer_profile нет параметра id
        "must_not_use": ["get_customer_profile"],
        "answer_any": ["иван"],
        "max_calls": 2,
    },
    {
        "q": "Найди клиента, имя начинается на 'Ол'",
        "must_use": ["query_sql"],            # exact match не подходит — нужен LIKE
        "must_not_use": ["get_customer_profile"],
        "answer_any": ["ольга","нет заказ", "нет никаких заказ", "нет активных заказ", "не имеет заказ", "отсутствуют заказ"],
        "max_calls": 2,
    },
    {
        "q": "Есть ли клиент по имени Анна?",
        "must_use": ["get_customer_profile"],
        "must_not_use": [],
        "answer_any": ["да", "есть", "найден"],
        "max_calls": 1,
    },
]


# ---------------------------------------------------------------------------
# Прогон одной задачи: возвращаем трассировку (transcript) для анализа.
# ---------------------------------------------------------------------------
def run_task(task: dict, tools: list) -> dict[str, Any]:
    input_list = [{"role": "user", "content": task["q"]}]
    calls: list[dict] = []        # [{name, args, result}]
    final_text = ""
    t0 = time.time()

    response = get_response(tools, input_list)
    for _ in range(MAX_STEPS):
        input_list += response.output
        tool_calls = [i for i in response.output if i.type == "function_call"]

        if not tool_calls:
            final_text = response.output_text
            break

        for tc in tool_calls:
            try:
                args = json.loads(tc.arguments)
                result = call_function(tc.name, args)
            except Exception as exc:
                result = {"error": str(exc)}
            calls.append({"name": tc.name, "args": tc.arguments, "result": result})
            input_list.append({
                "type": "function_call_output",
                "call_id": tc.call_id,
                "output": json.dumps(result, ensure_ascii=False),
            })
        response = get_response(tools, input_list)

    used = [c["name"] for c in calls]
    errors = sum(1 for c in calls if "error" in c["result"])
    selection_ok = (
        all(t in used for t in task["must_use"])
        and not any(t in used for t in task["must_not_use"])
    )
    answer = final_text.lower()
    answer_ok = (not task["answer_any"]) or any(s in answer for s in task["answer_any"])

    return {
        "question": task["q"],
        "tools_used": used,
        "n_calls": len(calls),
        "tool_errors": errors,
        "selection_ok": selection_ok,
        "answer_ok": answer_ok,
        "final_text": final_text,
        "elapsed_s": round(time.time() - t0, 2),
        "trace": calls,           # полная трассировка — пригодится для разбора
    }


def main():
    OUT_DIR = BASE_DIR/ "eval_results.json"
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3, help="прогонов каждой задачи")
    parser.add_argument("--out", default=OUT_DIR)
    args = parser.parse_args()

    results = []
    for task in TASKS:
        for run in range(1, args.runs + 1):
            print(f"[run {run}/{args.runs}] {task['q'][:50]}...")
            results.append(run_task(task, tools=openai_tools))

    # ----------------------------- отчёт -----------------------------
    print("\n" + "=" * 72)
    print(f"{'ЗАДАЧА':<45}{'ВЫБОР':>8}{'ОТВЕТ':>8}{'ВЫЗОВЫ':>9}{'ОШИБКИ':>8}")
    print("=" * 72)
    total_sel = total_ans = total_calls = total_err = 0
    for task in TASKS:
        rs = [r for r in results if r["question"] == task["q"]]
        sel = sum(r["selection_ok"] for r in rs)
        ans = sum(r["answer_ok"] for r in rs)
        avg_calls = sum(r["n_calls"] for r in rs) / len(rs)
        errs = sum(r["tool_errors"] for r in rs)
        total_sel += sel; total_ans += ans
        total_calls += sum(r["n_calls"] for r in rs); total_err += errs
        name = task["q"][:42] + ("..." if len(task["q"]) > 42 else "")
        print(f"{name:<45}{f'{sel}/{len(rs)}':>8}{f'{ans}/{len(rs)}':>8}"
              f"{avg_calls:>9.1f}{errs:>8}")

    n = len(results)
    print("=" * 72)
    print(f"ИТОГО: выбор инструмента {total_sel}/{n} ({total_sel/n:.0%}), "
          f"ответы {total_ans}/{n} ({total_ans/n:.0%}), "
          f"вызовов всего {total_calls}, ошибок инструментов {total_err}")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Трассировки сохранены в {args.out}")


if __name__ == "__main__":
    main()

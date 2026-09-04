from openai import OpenAI
from dotenv import load_dotenv
import os
import argparse
from pydantic import BaseModel, Field
from typing import List
import sys
import openai
import json
import time
from datetime import datetime
from pathlib import Path

load_dotenv("../.env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL_MAP = {
    "cheap": "gpt-4o-mini",
    "flagship": "gpt-4o",
}

PRICES = {
   
    "gpt-4o": {           
        "input":  2.50e-6,
        "cached": 1.25e-6,
        "output": 10.00e-6,
    },
    "gpt-4o-mini": {     
        "input":  0.15e-6,
        "cached": 0.075e-6,
        "output": 0.60e-6,
    },
    
}

class GroundedFact(BaseModel):
    quote: str  = Field(description="Точная цитата из исходного текста")
    summary: str   = Field(description="Краткий тезис или вывод на основе этой цитаты")

class ActionItem(BaseModel):
    quote: str   = Field(description="Цитата из текста, где упоминается задача или поручение")
    action: str = Field(description="Сформулированная задача (что сделать)")
    assignee : str | None = Field(description="кто ответственный (если указан в тексте, иначе null)")
    deadline: str| None = Field(description="срок (если указан, иначе null)")

class SummaryResults(BaseModel):
    key_points: List[GroundedFact] = Field(description="Основные тезисы с привязкой к цитатам")
    action_items:List[ActionItem] = Field(description="Список задач/действий с привязкой к цитатам")
    topics: List[str] = Field(description="Ключевые темы текста")



system_prompt = """
<task>
Ты — эксперт по анализу и суммаризации текстов.
Твоя задача проанализировать входной текст и извлечь из него ключевые тезисы, действия и темы.
</task>
<format>
    <schema>
        Ты должен вернуть JSON, строго соответствующий следующей структуре:

        1. key_points (список объектов): Основные смысловые тезисы текста.
        Каждый объект содержит:
        - quote (string): Точная дословная цитата из текста.
        - summary (string): Краткая суть или вывод на основе этой цитаты.

        2. action_items (список объектов): Поручения, задачи или договоренности.
        Каждый объект содержит:
        - quote (string): Дословная цитата, где упоминается задача.
        - action (string): Понятно сформулированное действие (что нужно сделать).
        - assignee (string или null): Имя/роль ответственного (только если прямо указаны в тексте).
        - deadline (string или null): Срок исполнения (только если прямо указан в тексте).

        3. topics (список строк): Список из 3–5 ключевых тем или тегов текста.
    </schema>
    <rules>
        1. Для каждого тезиса ты ОБЯЗАН сначала найти точную цитату из текста, не делай пересказ
        2. Механика цитата -> вывод. Сначала найди точную цитату и скопируй в 'quote'. 
            затем сформируй вывод/задачу
        3. НЕЛЬЗЯ ничего выдумывать если в тексте не прописаны действия/исполнитель/срок используй null
        4. Не добавляй тезисов которых нет в тексте
        5. Ответы должны быть в формате JSON, без MARKDOWN и без комментариев Первый символ ответа — {, последний — }. Никакого текста до или после JSON.
        6. Если текст представляет собой список задач или пунктов, каждый пункт одновременно является и тезисом (фактом), и действием. Выноси его и в key_points (как факт), и в action_items (как задачу).
        7. Поле action должно быть прямо выводимо из quote. Если в цитате нет глагола действия, найди другую цитату.
     </rules>
</format>

<example>
    <input>
        Из протокола встречи команды разработки (4 сентября 2026 г.):
        «Коллеги, обсудили текущий статус по релизу. Нам нужно оптимизировать SQL-запросы в модуле бронирования, 
        так как при нагрузке больше 100 пользователей сервер начинает тормозить. Иван, возьми эту задачу и сделай 
        профилирование базы до следующего вторника. Также Мария должна обновить документацию по API для интеграции 
        с платежным шлюзом к 12 сентября, иначе партнёры не смогут начать тесты. В целом встреча прошла 
        продуктивно, все текущие блокировки разобрали.»
    </input>
    <output>
        {
    "key_points": [
            {
            "quote": "Нам нужно оптимизировать SQL-запросы в модуле бронирования, так как при нагрузке больше 100 пользователей сервер начинает тормозить.",
            "summary": "Сервер тормозит при нагрузке выше 100 пользователей из-за неоптимизированных SQL-запросов в модуле бронирования."
            },
            {
            "quote": "В целом встреча прошла продуктивно, все текущие блокировки разобрали.",
            "summary": "На встрече успешно разобрали все текущие блокирующие проблемы."
            }
        ],
        "action_items": [
            {
            "quote": "Иван, возьми эту задачу и сделай профилирование базы до следующего вторника.",
            "action": "Сделать профилирование базы данных и оптимизировать SQL-запросы в модуле бронирования.",
            "assignee": "Иван",
            "deadline": "до следующего вторника"
            },
            {
            "quote": "Также Мария должна обновить документацию по API для интеграции с платежным шлюзом к 12 сентября",
            "action": "Обновить документацию по API для интеграции с платежным шлюзом.",
            "assignee": "Мария",
            "deadline": "12 сентября"
            }
        ],
        "topics": [
            "Оптимизация производительности SQL",
            "Обновление API документации",
            "Статус релиза"
        ]
            }
        </output>
</example>
"""

user_prompt = "<input_text>[TEXT_DATA]</input_text>"
def print_pretty_summary(data: dict, model_name: str, cost: float):
    result: SummaryResults = data["result"]
    
    print("\n" + "=" * 50)
    print(f"📊 РЕЗУЛЬТАТ ОБРАБОТКИ | Модель: {model_name}")
    print("=" * 50)
    

    print(result.model_dump_json(indent=2, ensure_ascii=False))
    
    print("-" * 50)
    print(f"⏱️  Время ответа:    {data['elapsed_time']:.2f} сек")
    print(f"📥 Prompt tokens:    {data['prompt_tokens']}")
    print(f"📤 Completion tokens: {data['completion_tokens']}")
    print(f"💰 Эстимейт стоимости: ${cost:.6f}")
    print("=" * 50 + "\n")

def save_to_jsonl(data: dict, model_name: str, cost: float, filepath: str = "eval_results.jsonl", ):
    result: SummaryResults = data["result"]
    
    # Формируем плоский словарь для логов
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "model": model_name,
        "metrics": {
            "elapsed_time": round(data["elapsed_time"], 3),
            "prompt_tokens": data["prompt_tokens"],
            "completion_tokens": data["completion_tokens"],
            "cost_usd": round(cost, 6)
        },
        # Превращаем Pydantic-объект в dict для сериализации
        "data": result.model_dump()
    }
    
    # Записываем строкой в конец файла (a = append)
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        
    print(f"📁 Результат сохранен в {filepath}")

def get_response(model:str, text_data:str):

    final_user_prompt = user_prompt.replace("[TEXT_DATA]", text_data)

    try: 
        start_time = time.perf_counter()
        # print(f"DEBUG: длина текста = {len(text_data)} символов")
        # print(f"DEBUG: первые 100 символов user_prompt = {final_user_prompt[:100]}")
        response = client.responses.parse(
            model=model,
            temperature=0.0,
            text_format=SummaryResults,
            input=[{
                "role" : "system",
                "content" : system_prompt,
            },
                   {
                "role": "user",
                "content": final_user_prompt,
            }],
            
        )
        # print("DEBUG: raw output_text:")
        # print(response.output_text)     
        result = response.output_parsed

        

        end_time = time.perf_counter()
        elapsed_time = end_time - start_time

        input_tokens = 0
        output_tokens = 0
        if response.usage:
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens



        return {
            "result": result,
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "elapsed_time": elapsed_time,
        }
    
    except openai.RateLimitError as e:
        print(f"\n[429 Rate Limit] Лимит запросов: {e.message}. Подождите и повторите.")
    except (openai.APIConnectionError, openai.APITimeoutError) as e:
        print(f"\n[Сеть/таймаут] Проблема с соединением к OpenAI: {e}")
    except openai.APIError as e:
        print(f"\n[API Error OpenAI {e.status_code}] {e.message}")
    except Exception as e:
        print(f"\n[Системная ошибка] {type(e).__name__}: {e}")




def main():
    parser = argparse.ArgumentParser(description="CLI SDK")

    parser.add_argument(
        "--model",
        type=str,
        choices=["cheap", "flagship"],
        default="cheap",
        help="Выбор типа модели"
    )

    parser.add_argument(
        "--file", 
        "-f", 
        type=str, 
        help="Путь к файлу с текстом"
    )

    args = parser.parse_args()

    model_type = args.model
    model = MODEL_MAP[model_type]
    

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()

    else:

        if not sys.stdin.isatty():
            text = sys.stdin.read()
        else:
            print("Ошибка: не указан --file и нет данных в stdin")
            sys.exit(1)

    
    response_data = get_response(model, text)

    if response_data is not None:
        rates = PRICES[model]
        cost = (response_data["prompt_tokens"] * rates["input"]) + (response_data["completion_tokens"] * rates["output"])
        
        # 2. Вывод в терминал
        print_pretty_summary(response_data, model, cost)
        
        # 3. Сохранение в файл
        save_to_jsonl(response_data, model, cost, filepath="runs_history.jsonl")



if __name__ == "__main__":
    main()
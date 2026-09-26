from openai import OpenAI
from anthropic import Anthropic
from dotenv import load_dotenv, find_dotenv
import os
import json
import sqlite3
from typing import Any, Dict
from pathlib import Path
load_dotenv(find_dotenv())

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

ALLOWED_TABLES = {"customers", "orders"}
MAX_LIMIT = 5
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR /"shop.db"  

questions = [
    "Сколько заказов у Анны и что она купила?",
    "Какие заказы у Ольги?",
    "Сколько потратила Мария?",
    "У кого больше заказов — у Анны или у Ивана?",
    "Покажи заказы клиента, который купил наушники",
    "Сколько всвего оплат в таблице payments",
]


openai_tools = [
    {
    "type": "function", 
    "name": "query_sql",
    "description": "Executes read-only SQL SELECT queries against the local SQLite database containing 'customers'"
                    "and 'orders' tables. Use this tool to retrieve customer profile details or order details using standard SQL queries."
                    " Only SELECT queries are permitted; data modification or schema alterations will result in an error. "
                    "Always limit the results using a LIMIT clause or specific filters to ensure concise outputs."
                    " Database schema: customers(customer_id INTEGER PK, name TEXT, city TEXT, registered TEXT); "
                    "orders(order_id INTEGER PK, customer_id INTEGER FK → customers, product TEXT,amount REAL, "
                    "status TEXT ['delivered','shipped','cancelled','processing'], created_at TEXT)."
                    "Note: orders with status 'cancelled' represent refunded/cancelled purchases — exclude them when computing spending",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The read-only SQL SELECT query to execute against the SQLite database (e.g., 'SELECT * FROM customers WHERE customer_id = 1 LIMIT 5')."
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "strict": True   
    },
    {
    "type": "function",
    "name": "get_customer_profile",
    "description": "Retrieves the profile details of a single customer from the read-only SQLite database by their exact name. "
            "Use this tool to quickly look up a customer's basic information (customer_id, name, city, registered) without writing raw SQL. "
            "This is especially useful for finding a 'customer_id' to use as a foreign key in subsequent order queries. Note: The search requires an exact text match for the name."
            "Do NOT use this tool for order queries, aggregations, or listing multiple customers — use query_sql instead.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
            "type": "string",
            "description": "The exact name of the customer to search for in the database (e.g., 'Мария' or 'Иван')."
            }
        },
        "required": ["name"],
        "additionalProperties": False
        },
        "strict": True
  }
]



def query_sql(query: str) -> Dict[str, Any]:
    normalized_query = query.strip().lower()

    # 1. Валидация SELECT
    if not normalized_query.startswith("select"):
        return {
            "error": "SecurityError: Разрешены только SELECT-запросы.",
        }

    # 2. Проверка белого списка таблиц
    tokens = [t.strip(";,()\"'") for t in normalized_query.split()]
    for keyword in ["from", "join"]:
        if keyword in tokens:
            idx = tokens.index(keyword) + 1
            if idx < len(tokens) and tokens[idx] not in ALLOWED_TABLES:
                return {
                    "error": f"SecurityError: Доступ к таблице '{tokens[idx]}' запрещен. Разрешено: {ALLOWED_TABLES}",
                }

    # 3. Безопасное подключение в режиме Read-Only
    try:
        conn = sqlite3.connect(
            f"file:{DB_PATH}?mode=ro", uri=True
        )
        cursor = conn.cursor()

        # Подстановка/контроль LIMIT
        exec_query = (
            query if "limit" in normalized_query else f"{query.rstrip(';')} LIMIT {MAX_LIMIT + 1}"
        )

        cursor.execute(exec_query)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        truncated = len(rows) > MAX_LIMIT
        result_rows = rows[:MAX_LIMIT] if truncated else rows
        results = [dict(zip(columns, row)) for row in result_rows]

        return {
            "status": "success",
            "rows_count": len(results),
            "truncated": truncated,
            "data": results,
        }

    except sqlite3.OperationalError as e:
        return { "error": f"sqlite3.OperationalError: {str(e)}"}
    finally:
        if "conn" in locals():
            conn.close()

def get_customer_profile(name: str) -> Dict[str, Any]:
    """Тот же read-only доступ, но точечный: один клиент по имени."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        cursor = conn.execute(
            "SELECT customer_id, name, city, registered FROM customers WHERE name = ? LIMIT 1",
            (name,),
        )
        row = cursor.fetchone()
        if row is None:
            return {"error": f"Клиент с именем '{name}' не найден. Проверь написание."}
        return {"status": "success", "data": dict(zip(
            ["customer_id", "name", "city", "registered"], row))}
    finally:
        conn.close()


ROUTER  = {
    "query_sql" : query_sql,
    "get_customer_profile" :get_customer_profile
}


def get_response(tools: list[dict[str, Any]],input_list ):
    return openai_client.responses.create(
    model="gpt-4o-mini",
    tools=tools,
    input=input_list,
    tool_choice="auto",
    parallel_tool_calls=False
)


def call_function(name:str, args):
    fn = ROUTER.get(name)
    if fn is None:
       return {"error": f"unknown function: {name}"}
    return fn(**args)


MAX_STEPS = 5

def run_question(q: str):
    input_list = [{"role": "user", "content": q}]
    response = get_response(openai_tools, input_list)

    for step in range(MAX_STEPS):
        input_list += response.output                      
        tool_calls = [i for i in response.output if i.type == "function_call"]

        if not tool_calls:                                
            print("ОТВЕТ:", response.output_text)
            return

        for tc in tool_calls:                               
            try:
                print(f"  [шаг {step+1}] {tc.name} (call_id={tc.call_id}): {tc.arguments}")
                args = json.loads(tc.arguments)
                result = call_function(tc.name, args)
            except Exception as exc:
                result = {"error": str(exc)}                
            print(f"  [шаг {step+1}] результат → {json.dumps(result, ensure_ascii=False)[:200]}")
            input_list.append({
                "type": "function_call_output",
                "call_id": tc.call_id,
                "output": json.dumps(result, ensure_ascii=False),  
            })

        response = get_response(openai_tools, input_list)  

    print("СТОП: исчерпан лимит шагов")

if __name__ == "__main__":
    for q in questions:
        print(f"\n=== {q}")
        run_question(q)


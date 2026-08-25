import asyncio 
import json
import os
import websockets 
from dotenv import load_dotenv


load_dotenv("../.env")


OPEN_AI_KEY = os.getenv("OPENAI_API_KEY")

WS_URL = "wss://api.openai.com/v1/responses"


async def run_agent_session():
    headers = {
        "Authorization" : f"Bearer {OPEN_AI_KEY}"
    }

    async with websockets.connect(WS_URL, additional_headers = headers) as ws:
        print("✅ Соединение установлено.")


        warmup_event = {
            "type": "response.create",
            "stream_id" : "main_thread",
            "model": "gpt-4o",
            "store": False,
            "generate" : False,
            "input" :[
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "Ты — Dev Agent. Используй инструменты."}]
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "name": "read_file",
                    "description": "Чтение содержимого файла",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"]
                    }
                }
            ]
        }   

        await ws.send(json.dumps(warmup_event))



        response_raw = await ws.recv()
        warmup_ack = json.loads(response_raw)

  
        if warmup_ack.get("type") == "error" or "error" in warmup_ack:
            print(f"❌ Ошибка от OpenAI API: {json.dumps(warmup_ack, indent=2)}")
            return

        warmup_resp_id = warmup_ack.get("id") or warmup_ack.get("response", {}).get("id")
        
        print(f"🔥 Warmup зафиксирован. Parent ID: {warmup_resp_id}")
        first_turn = {
            "type": "response.create",
            "stream_id": "main_thread",
            "model": "gpt-4o",
            "store": False,
            "previous_response_id": warmup_resp_id, # Ссылка на warmup
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Прочитай файл main.py"}]
                }
            ]
        }
        await ws.send(json.dumps(first_turn))


        tool_call_id = None
        last_response_id = None

       
        while True:
            msg = json.loads(await ws.recv())
            event_type = msg.get("type")

            if event_type == "response.output_item.added":
                item = msg.get("item", {})
                if item.get("type") == "function_call":
                    tool_call_id = item.get("call_id")
                    print(f"🛠 Модель запросила Tool Call ID: {tool_call_id}")

            elif event_type == "response.done":
                last_response_id = msg["response"]["id"]
                print(f"🏁 Шаг 1 завершен. Response ID: {last_response_id}")
                break

        if tool_call_id:
            tool_response_turn = {
                "type": "response.create",
                "stream_id": "main_thread",
                "model": "gpt-4o",
                "store": False,
                "previous_response_id": last_response_id, 
                "input": [
                    {
                        "type": "function_call_output",
                        "call_id": tool_call_id,
                        "output": "def main(): print('Hello World')" 
                    }
                ]
            }
            await ws.send(json.dumps(tool_response_turn))

        
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("type") == "response.text.delta":
                    print(msg.get("delta"), end="", flush=True)
                elif msg.get("type") == "response.done":
                    print("\n✅ Цепочка завершена.")
                    break

if __name__ == "__main__":
    asyncio.run(run_agent_session())
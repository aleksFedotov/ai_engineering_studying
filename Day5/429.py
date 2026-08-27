import asyncio
from openai import AsyncOpenAI, RateLimitError,NotFoundError, APIStatusError
import requests
from dotenv import load_dotenv
import os
load_dotenv("../.env")

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),  
    max_retries=0, 
)

models = requests.get(
    "https://openrouter.ai/api/v1/models",
    headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"},
).json()["data"]
PREFERRED = ("llama", "qwen", "gemma", "mistral", "deepseek", "gpt", "glm")
free = [m["id"] for m in models if m["id"].endswith(":free")]
FREE_MODEL = next(
    (m for m in free if any(p in m for p in PREFERRED)),
    free[0],
)
print(f"Используем модель: {FREE_MODEL}")


async def one_rq(i :int):
    try:
        r = await client.chat.completions.create(
            model=FREE_MODEL,
            messages=[{"role": "user", "content": f"Скажи число {i}"}],
            max_tokens=10,
        )

        print(r.model_dump_json(indent=2))

        print(f"[{i}] OK: {r.choices[0].message.content!r}")
    except RateLimitError as e:
        print(f"[{i}] 429!")
        print(f"    message: {e.message}")
        print(f"    body: {e.body}")
        print(f"    headers: {dict(e.response.headers)}")
    except NotFoundError as e:
        print(f"[{i}] 404 (не ретраим): {e.message}")

    except APIStatusError as e:
        print(f"[{i}] {e.status_code}: {e.message}")

async def main():
    # await one_rq(1)
     await asyncio.gather(*[one_rq(i) for i in range(30)])

asyncio.run(main())
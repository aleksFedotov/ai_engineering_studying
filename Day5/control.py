import asyncio
import logging
import random
import openai

from dotenv import load_dotenv
from openai import AsyncOpenAI, RateLimitError,APITimeoutError,APIConnectionError, InternalServerError, APIStatusError


load_dotenv("../.env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("checkpoint")

client = AsyncOpenAI(
    base_url="http://localhost:8899/v1",
    api_key="fake",
    max_retries=2,
    timeout=5.0,
)



async def resilient_call(i: int) -> str:
    for attempt in range(1,6):
        try:
            r = await client.chat.completions.create(
                model="mock",
                messages= [{"role": "user", "content" :  f"task {i}"}]
            )

            return f"[{i}] OK: {r.choices[0].message.content}"

        except RateLimitError as e:
            ra = e.response.headers.get("retry-after")

            if ra is None:
                return f"[{i}] FAIL: spend cap (request_id={e.request_id})"

            delay = float(ra) + random.uniform(0,0.5)
            log.info("[%d] 429, жду %.1fs (request_id=%s)", i, delay, e.request_id)
        except (APITimeoutError,  APIConnectionError,InternalServerError) as e:
            delay = min(30, 2 ** attempt) + random.uniform(0, 0.5)
            log.info("[%d] %s, жду %.1fs", i, type(e).__name__, delay)
        except APIStatusError as e:
            return f"[{i}] FAIL: {e.status_code} {e.message} (request_id={e.request_id})"

        await asyncio.sleep(delay)
    return f"[{i}] FAIL: попытки исчерпаны"


async def main():
    result = await asyncio.gather(*[resilient_call(i) for i in range(10)])
    ok =sum(1 for r in result if "OK" in r)
    for r in result:
        print(r)
    print(f"\nИтог: {ok}/10 успешно. Скрипт не упал ✔")

asyncio.run(main())

    

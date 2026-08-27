import asyncio
from openai import AsyncOpenAI,RateLimitError, InternalServerError,APITimeoutError,APIConnectionError,APIStatusError 
import logging
import random 
from dotenv import load_dotenv
import os


load_dotenv("../.env")


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("llm")

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MAX_ATTEMPTS = 5          
BASE_DELAY = 1.0
MAX_DELAY = 60.0

async def call_with_retry(messages, model = "gpt-4o-mini"):

    for attempt in range(1, MAX_ATTEMPTS +1):
    
        try:
            return await client.chat.completions.create(
                messages=messages,
                model=model
            )
        # --- Ретраибельные: 429 ---
        except RateLimitError as e:
            retry_after = e.response.headers.get("retry-after")
            log.warning(
                "429 rate_limit | attempt=%d/%d | request_id=%s | retry_after=%s | msg=%s",
                attempt, MAX_ATTEMPTS, e.request_id, retry_after, e.message,
            )

            if retry_after is None:
                log.error("429 без retry-after: вероятно, потолок трат. Стоп.")
                raise
            delay = float(retry_after) + random.uniform(0, 1)
        # --- Ретраибельные: 5xx, таймауты, сеть ---
        except (InternalServerError, APITimeoutError, APIConnectionError) as e:
            log.warning(
                "%s | attempt=%d/%d | request_id=%s",
                type(e).__name__, attempt, MAX_ATTEMPTS,
                getattr(e, "request_id", None),
            )
        # Экспоненциальный backoff: 1s, 2s, 4s, 8s... + jitter
            delay = min(MAX_DELAY, BASE_DELAY * 2 ** (attempt - 1)) + random.uniform(0, 1)    

        # --- НЕретраибельные: 400/401/402/403/404/413/422 ---        
        except APIStatusError as e:
            log.error(
                "%s (не ретраим) | status=%d | request_id=%s | msg=%s",
                type(e).__name__, e.status_code, e.request_id, e.message,
            )
            raise

        if attempt == MAX_ATTEMPTS:
            log.error("Попытки исчерпаны (%d)", MAX_ATTEMPTS)
            raise RuntimeError("Max attempts exceeded")


        log.info("sleep %.1fs перед попыткой %d", delay, attempt + 1)
        await asyncio.sleep(delay)
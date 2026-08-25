import asyncio
import os
from typing import AsyncGenerator
from openai import AsyncOpenAI

from dotenv import load_dotenv


load_dotenv('../.env')

client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))

async def stream_openai_response(prompt: str) -> AsyncGenerator[str, None]:
    """
    Асинхронный генератор для обработки события потока Responses API.
    """

    try:
        steam = await client.responses.create(
            model = "gpt-5.6",
            input= [
                {"role": "developer", "content": "You are an expert systems architect."},
                {"role": "user", "content": prompt}
            ],
            stream=True
        )

        async for event in steam:

            event_type = getattr(event, "type", None)

            if event_type == "response.created":
                print(f"\n[SYS] Response initiated: {event.response.id}")

            elif event_type == "response.output_text.delta":
                # Доступ к тексту дельты
                delta_text = getattr(event, "delta", "")
                if delta_text:
                    yield delta_text

            elif event_type == "response.completed":
                print("\n[SYS] Completed.")

            elif event_type == "error":
                print(f"\n[ERROR] Stream error: {event.error}")

    except Exception as e:
        print(f"[FATAL] Connection or execution error: {str(e)}")
        raise e


async def main():
    pront = "Объясни архитектуру распределенного кэширования"   
    prompt = "Объясни архитектуру распределенного кэширования."
    print("--- Start Streaming ---")
    async for chunk in stream_openai_response(prompt):
        print(chunk, end="", flush=True)
    print("\n--- End Streaming ---")

if __name__ == "__main__":
    asyncio.run(main())
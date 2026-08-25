import time 
from openai import OpenAI
from anthropic import Anthropic
import os
from dotenv import load_dotenv

load_dotenv('../.env')

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
anthropic_client = Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))



def test_openai_stream(prompt:str):
    print("--- OpenAI Streaming ---")
    start_time = time.perf_counter()
    first_token_time = None
    stream = openai_client.chat.completions.create(
        model='gpt-4o',
        stream=True,
        messages=[{"role": "user", "content": prompt}]
    )

    for chunk in stream:
        # Извлекаем текст из delta
        content = chunk.choices[0].delta.content
        if content: 
            if first_token_time is None:
                first_token_time = time.perf_counter()
            print(content, end="", flush=True)

    end_time = time.perf_counter()
    ttft = first_token_time - start_time if first_token_time else 0
    total_time = end_time - start_time
    print(f"\n\n[OpenAI] TTFT: {ttft:.3f}s | Total Time: {total_time:.3f}s\n")


def test_anthropic_stream(prompt: str):
    print("--- Anthropic Streaming ---")
    start_time = time.perf_counter()
    first_token_time = None


    with anthropic_client.messages.stream(
        model="claude-opus-5",
        max_tokens=2048,
        messages=[{"role":"user", "content" : prompt}]
    ) as stream:
        for text in stream.text_stream:
            if first_token_time is None:
                first_token_time = time.perf_counter()
            print(text, end="", flush=True)

        final_message = stream.get_final_message()

    end_time = time.perf_counter()

    ttft = first_token_time - start_time if first_token_time else 0
    total_time = end_time - start_time
    print(f"\n\n[Anthropic] TTFT: {ttft:.3f}s | Total Time: {total_time:.3f}s")
    print(f"Stop reason: {final_message.stop_reason} | Output tokens: {final_message.usage.output_tokens}\n")


if __name__ == "__main__":
    prompt = "Напиши подробный конспект по архитектуре LLM на 1000 слов."
    test_openai_stream(prompt)
    test_anthropic_stream(prompt)
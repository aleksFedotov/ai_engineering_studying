from openai import OpenAI,AsyncOpenAI,RateLimitError,APITimeoutError,APIConnectionError, InternalServerError, APIStatusError
from dotenv import load_dotenv
from typing import AsyncGenerator
import asyncio
import os

load_dotenv('../.env')

PRICES = {
    # OpenAI
    "gpt-5.6-sol":    {"input": 5.00e-6,  "cached": 0.50e-6,  "output": 30.00e-6},
    "gpt-5.6-terra":  {"input": 2.00e-6,  "cached": 0.20e-6,  "output": 12.00e-6},
    "gpt-5.6-luna":   {"input": 0.20e-6,  "cached": 0.02e-6,  "output": 1.20e-6},
    # Anthropic
    "claude-fable-5":  {"input": 10.0e-6, "cached": 1.00e-6, "cache_write": 12.50e-6, "output": 50.00e-6},
    "claude-opus-5":   {"input": 5.00e-6, "cached": 0.50e-6, "cache_write": 6.25e-6,  "output": 25.00e-6},
    "claude-sonnet-5": {"input": 2.00e-6, "cached": 0.20e-6, "cache_write": 2.50e-6,  "output": 10.00e-6},
    "claude-haiku-4.5":{"input": 1.00e-6, "cached": 0.10e-6, "cache_write": 1.25e-6,  "output": 5.00e-6},
}

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))



def calculate_cost(model: str, usage) -> float:
    p = PRICES[model]
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    input_details = getattr(usage, "input_tokens_details", None)  
    cached_tokens = (getattr(input_details, "cached_tokens", 0) or 0) if input_details else 0

    fresh_input = input_tokens - cached_tokens
    return fresh_input * p["input"] + cached_tokens * p["cached"] + output_tokens * p["output"]


def openai_usage(model: str, prompt: str) -> float:
    try:
        res = client.responses.create(
            model=model,
            input=[{"role": "user", "content": prompt}],
        )
        u = res.usage
        print(f"[{model}] in={u.input_tokens} (cached={u.input_tokens_details.cached_tokens}), out={u.output_tokens}, reasoning={u.output_tokens_details.reasoning_tokens}")
        print(f"Ответ: {res.output_text[:100]}...")
        return calculate_cost(model, u)
    except RateLimitError as e:
        print(f"[429] Лимит: {e}")
        raise
    except (APITimeoutError, APIConnectionError, InternalServerError) as e:
        print(f"[NET/5xx] {e}")
        raise


    


def main():
    luna_cost = openai_usage("gpt-5.6-luna", "Объясни архитектуру распределенного кэширования.")
    sol_cost = openai_usage("gpt-5.6-sol", "Объясни архитектуру распределенного кэширования.")
    print(f"Luna: ${luna_cost:.6f}")
    print(f"Sol:  ${sol_cost:.6f}")
    if luna_cost > 0:
        print(f"Разница: ${sol_cost - luna_cost:.6f}, Sol дороже в {sol_cost / luna_cost:.1f}x")

if __name__ == "__main__":
    main()
from openai import OpenAI
import openai
from anthropic import Anthropic
import anthropic
from dotenv import load_dotenv
from typing import Iterator
import argparse
import os

load_dotenv("../.env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("CLAUDE_API_KEY")

openai_client = OpenAI(api_key=OPENAI_API_KEY)
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

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

DEFAULT_MODELS = {"openai": "gpt-5.6-luna", "anthropic": "claude-sonnet-5"}
DEFAULT_SYSTEM = "Ты дружелюбный ассистент. Отвечай кратко."

history: list[dict] = []  
session_cost = 0.
        
openai_history =[
    {
        "role" : "system",
        "content": "Ты дружелюбный ассистент. Отвечай кратко.",
    }
]
anthropic_history = []


def openai_stream(model: str,prompt:str, system: str) -> Iterator[str]:
    history.append({"role": "user", "text": prompt})
    full_response = ""
    stream = None
    try:
        messages = [{"role": "system", "content": system}] + [
                    {"role": m["role"], "content": m["text"]} for m in history
                ]
        stream = openai_client.responses.create(
            model=model,
            input=messages,
            stream=True
        )
        final_usage = None
        for chunk in stream:
            if chunk.type == "response.output_text.delta":
                text_delta = chunk.delta
                if text_delta:
                    full_response += text_delta
                    yield text_delta

            elif chunk.type == "response.completed":
                final_usage = chunk.response.usage
        if final_usage:
            p = PRICES[model]
            input_tokens = getattr(final_usage, "input_tokens", 0) or 0
            output_tokens = getattr(final_usage, "output_tokens", 0) or 0
            details = getattr(final_usage, "input_tokens_details", None)
            cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
            fresh = input_tokens - cached
            cost = fresh * p["input"] + cached * p["cached"] + output_tokens * p["output"]
            _report(input_tokens=fresh, output_tokens=output_tokens,
                    cached=cached, cost=cost)
        else:
            print("[WARNING] Стрим завершился без события response.completed — usage неизвестен")

       
    except openai.RateLimitError as e:
        # 429: лимит не снялся даже после автоматических ретраев SDK
        print(f"\n[429 Rate Limit] Лимит запросов: {e.message}. Подождите и повторите.")
    except (openai.APIConnectionError, openai.APITimeoutError) as e:
        print(f"\n[Сеть/таймаут] Проблема с соединением к OpenAI: {e}")
    except openai.APIError as e:
        # Всё остальное от API OpenAI: 400, 401, 5xx после ретраев и т.д.
        print(f"\n[API Error OpenAI {e.status_code}] {e.message}")
    except Exception as e:
        # Баги нашего собственного кода — не роняем чат
        print(f"\n[Системная ошибка] {type(e).__name__}: {e}")

    finally:
         if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
    if full_response:
        history.append({"role": "assistant", "text": full_response})
    else:
        # запрос не состоялся — убираем «вопрос без ответа» из истории
        history.pop()

def anthropic_stream(model: str,prompt:str,system: str)  -> Iterator[str]:
    history.append({"role": "user", "text": prompt})
    full_response = ""
    try:
        with anthropic_client.messages.stream(
            model=model,
            system= "Ты дружелюбный ассистент. Отвечай кратко.",
            max_tokens=1024,
            messages=[{"role": m["role"], "content": m["text"]} for m in history],
        ) as stream: 
            for text in stream.text_stream:
                full_response += text
                yield text

        usage = stream.get_final_message().usage
        if usage:
            p = PRICES[model]
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            # у Anthropic кэш — плоские поля usage (не input_tokens_details!)
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
            fresh = input_tokens - cache_read - cache_write
            cost = (fresh * p["input"]
                    + cache_read * p["cached"]
                    + cache_write * p.get("cache_write", p["input"])
                    + output_tokens * p["output"])
            _report(input_tokens=fresh, output_tokens=output_tokens,
                    cached=cache_read, cost=cost)

        
    except anthropic.RateLimitError as e:
        print(f"\n[429 Rate Limit] Лимит запросов: {e.message}. Подождите и повторите.")
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
        print(f"\n[Сеть/таймаут] Проблема с соединением к Anthropic: {e}")
    except anthropic.APIError as e:
        print(f"\n[API Error Anthropic {e.status_code}] {e.message}")
    except Exception as e:
        print(f"\n[Системная ошибка] {type(e).__name__}: {e}")
    finally:
        if full_response:
            history.append({"role": "assistant", "text": full_response})
        else:
            history.pop()



def _report(input_tokens: int, output_tokens: int, cached: int, cost: float) -> None:
    """Печать строки со статистикой и накопление стоимости сессии."""
    global session_cost
    session_cost += cost
    print(f"\n [токенов: {input_tokens} вх. / {output_tokens} вых. / "
          f"{cached} кэш. / ${cost:.6f} | сессия: ${session_cost:.6f}]")

def main():
    parser = argparse.ArgumentParser(description="CLI Chat SDK")
    
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic"],
        default="openai",
        help="Выбор провайдера"
    )
    
    # Флаг для задания системного промпта из консоли
    parser.add_argument(
        "--system",
        type=str,
        default=None,
        help="Инструкция для модели (system prompt)"
    )

    args = parser.parse_args()

    provider = args.provider
    model = DEFAULT_MODELS[provider]
    system = args.system

    print(f"--- Чат запущен ({provider}, {model}) ---")
    print("Команды: /provider openai|anthropic, /model <имя>, /cost, exit/quit")

    while True:
        try:
            # 1. Получаем ввод от пользователя
            user_input = input("\nВы: ").strip()

            # Обработка команд выхода
            if user_input.lower() in ["exit", "quit"]:
                print("Завершение сеанса...")
                break

            # Пропуск пустого ввода
            if not user_input:
                continue
            # --- служебные команды ---
            if user_input.startswith("/provider "):
                new = user_input.split(maxsplit=1)[1].strip().lower()
                if new in ("openai", "anthropic"):
                    provider = new
                    model = DEFAULT_MODELS[provider]
                    print(f"[провайдер: {provider} ({model}), "
                          f"история: {len(history)} сообщений перенесена]")
                else:
                    print("[ошибка] допустимо: /provider openai или /provider anthropic")
                continue

            if user_input.startswith("/model "):
                new_model = user_input.split(maxsplit=1)[1].strip()
                if new_model in PRICES:
                    model = new_model
                    print(f"[модель: {model}]")
                else:
                    print(f"[ошибка] неизвестная модель. Доступны: {', '.join(PRICES)}")
                continue

            if user_input == "/cost":
                print(f"[стоимость сессии: ${session_cost:.6f}]")
                continue

            print("Бот: ", end="", flush=True)

            if provider == "openai":
                stream = openai_stream(model, user_input, system)
            else:
                stream = anthropic_stream(model, user_input, system)
            for chunk in stream:
                print(chunk, end="", flush=True)


            print()  # Перевод строки в конце ответа

        except (KeyboardInterrupt, EOFError):
            # Обработка Ctrl+C / Ctrl+D для корректного выхода
            print("\nСеанс прерван.")
            break



if __name__ == "__main__":
    main()
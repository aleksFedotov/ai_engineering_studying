from openai import OpenAI
from dotenv import load_dotenv
import os
import openai
import argparse
from pydantic import BaseModel, Field,model_validator
from typing import Dict

load_dotenv("../.env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


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


TESTS = [
    # группа A — ответ есть
    {"q": "Сколько токенов заняла фраза «Привет, как дела?»?",
     "group": "A", "expect_found": True, "expect_source": "01-tokens.md"},
    {"q": "Какую температуру ставить для чата по заметкам?",
     "group": "A", "expect_found": True, "expect_source": "02-temperature.md"},
    {"q": "Что такое эффект lost in the middle?",
     "group": "A", "expect_found": True, "expect_source": "03-context-window.md"},
    {"q": "Как получить счётчик токенов при стриминге?",
     "group": "A", "expect_found": True, "expect_source": "08-streaming.md"},
    {"q": "Из каких этапов состоит RAG-пайплайн?",
     "group": "A", "expect_found": True, "expect_source": "05-rag.md"},
    # группа B — ловушки
    {"q": "Какая температура полностью убирает галлюцинации?",
     "group": "B", "expect_found": True, "expect_source": "07-hallucinations.md"},
    {"q": "Сколько примеров нужно для fine-tuning?",
     "group": "B", "expect_found": True, "expect_source": "10-fine-tuning.md"},
    {"q": "Чем RAG отличается от fine-tuning?",
     "group": "B", "expect_found": True, "expect_source": "10-fine-tuning.md"},
    # группа C — ответа нет
    {"q": "Что такое prompt injection?", "group": "C", "expect_found": False},
    {"q": "Какую векторную БД выбрать для RAG?", "group": "C", "expect_found": False},
]


NOTES_DIR = os.path.join(os.path.dirname(__file__), "notes")
session_cost = 0.


class Answer(BaseModel):
    quote_found: bool = Field(description="Найдена ли цитата, если не найдена False")
    quote: str | None = Field(description="Точная цитата из исходного текста если нет None")
    answer: str | None = Field(description="Ответ сформированный на основе цитаты если нет None")

    @model_validator(mode='after')
    def check_logical_consistency(self):
  
        if self.quote_found and (not self.quote or not self.answer):
            raise ValueError("quote_found=True, но цитата или ответ отсутствуют!")

        if not self.quote_found and (self.quote or self.answer):
            self.quote = None
            self.answer = None
        return self


def load_notes(folder_path:str):
    notes_content = []


    if not os.path.exists(folder_path):
        print(f"Ошибка: Папка {folder_path} не найдена!")
        return ""
    for filename in os.listdir(folder_path):
        if filename.endswith(".md"):
            file_path = os.path.join(folder_path, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                notes_content.append(f"--- Заметка: {filename} ---\n{content}\n")
    return "\n".join(notes_content)


notes_data = load_notes(NOTES_DIR)

system_promt =f"""

<task>
Ты — ассистент по персональным заметкам. Тебе передана подборка заметок пользователя в формате Markdown. 

Твоя задача отвечать на воросы пользователя используя ИСКЛЮЧИТЕЛЬНО инофрмацию из предоставленных заметок.
</task>
<rules>
    1. Ищи ответ только внутри предоставленных Markdown-текстов.
    2. Не используй свои фоновые знания для ответа на вопрос, если информации нет в заметках.
    3. Если ответ на вопрос отсутствует в предоставленных заметках, прямо ответь: «В предоставленных заметках нет информации по этому вопросу».
    4. При ответе Обязательно указывай заглавие или имя заметки (например, из заголовка `# Название`), откуда взята информация.
    5. Если ответ на вопрос существует ты ОБЯЗАН сначала найти точную цитату из текста, не делай пересказ
    6. Механика цитата -> ответ. Сначала найди точную цитату и используй ее для ответа. 
            затем сформируй ответ
    7.ИСКЛЮЧЕНИЕ: На светские фразы, приветствия и базовый разговор (например, «привет», «как дела?», «кто ты?») отвечай вежливо и кратко как дружелюбный ассистент, не обращаясь к заметкам.
</rules>

<notes>
{notes_data if notes_data else "Заметки не найдены или папка пуста."}
</notes>
"""

history = [{"role": "system", "content": system_promt},]


def _report(input_tokens: int, output_tokens: int, cached: int, cost: float) -> None:
    """Печать строки со статистикой и накопление стоимости сессии."""
    global session_cost
    session_cost += cost
    print(f"\n [токенов: {input_tokens} вх. / {output_tokens} вых. / "
          f"{cached} кэш. / ${cost:.6f} | сессия: ${session_cost:.6f}]")



def get_stream_response(model: str, user_input: str) :
    history.append({"role": "user", "text": user_input})
    full_response = ""
    stream = None
    try:
        messages = [
            {"role": m["role"], "content": m["text"]} for m in history
        ]
        stream =  client.responses.parse(
            model=model,
            stream= True,
            input=messages,
            text_format=Answer
        )
        final_usage = None
        for chunk in stream:
            if chunk.type == "response.output_text.delta":
                text_data = chunk.delta
                if text_data is None:
                    continue
                full_response += text_data
                yield text_data
            elif chunk.type == "response.completed":
                final_usage = chunk.response.usage

        if full_response:
            try:
                answer_obj = Answer.model_validate_json(full_response)

                is_quote_valid = (
                    answer_obj.quote_found 
                    and answer_obj.quote 
                    and (answer_obj.quote.strip() in notes_data)
                )

                if is_quote_valid:
                    final_output = f"📌 Цитата: {answer_obj.quote}\n💡 Ответ: {answer_obj.answer}"
                else:
                    final_output = "В предоставленных заметках нет информации по этому вопросу."

            except Exception as e:
            
                final_output = full_response 

            
            history.append({"role": "assistant", "text": final_output})
            yield final_output
        else:
            # Запрос завершился неудачей — убираем неответченный вопрос
            history.pop()

        if final_usage is not None: 
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
    # if full_response:
      
    #     history.append({"role": "assistant", "text": full_response})

    # else:
    #     # запрос не состоялся — убираем «вопрос без ответа» из истории
    #     history.pop()

def get_response(model: str, messages: list[dict])-> tuple[Answer, object]:
    res = client.responses.parse(
        model=model,
        input=messages,
        text_format= Answer
    )

    return res.output_parsed, res.usage


def check_expectations(answer_obj:Answer, t: dict) -> tuple[bool, str]:
    expect_found = t["expect_found"]
    expect_source = t.get("expect_source")

    # --- СЦЕНАРИЙ 1: Ожидали, что ответа НЕТ (Группа C) ---
    if not expect_found:
        if answer_obj.quote_found:
            return False, "Модель нашла ответ/цитату, хотя ответа не должно быть в заметках"
        if answer_obj.quote is not None or answer_obj.answer is not None:
            return False, "quote_found=False, но поля quote или answer не были сброшены в None"
        return True, "Ответ корректно не найден"

    # --- СЦЕНАРИЙ 2: Ожидали, что ответ ЕСТЬ (Группы A и B) ---
    if not answer_obj.quote_found:
        return False, "Модель не нашла ответ, хотя он есть в заметках"

    if not answer_obj.quote or not answer_obj.answer:
        return False, "quote_found=True, но поле quote или answer пустое (None)"

    # --- Проверка 2.1: Действительно ли цитата существует в оригинальном тексте заметок ---
    # Переменная notes_data должна быть доступна глобально или передаваться параметром
    if answer_obj.quote.strip() not in notes_data:
        return False, f"Галлюцинация цитаты: текст '{answer_obj.quote[:30]}...' отсутствует в заметках"

    # --- Проверка 2.2: Содержится ли упоминание нужного файла в ответе или цитате ---
    if expect_source:
        source_in_quote = expect_source in answer_obj.quote
        source_in_answer = expect_source in answer_obj.answer
        
        # Если имя файла не найдено напрямую, попробуем поискать заголовок без разрешения (например, "01-tokens")
        clean_source_name = os.path.splitext(expect_source)[0]
        clean_in_quote = clean_source_name in answer_obj.quote
        clean_in_answer = clean_source_name in answer_obj.answer

        if not (source_in_quote or source_in_answer or clean_in_quote or clean_in_answer):
            return False, f"Ответ найден, но нет ссылки на ожидаемый файл '{expect_source}'"

    return True, "Тест успешно пройден"

def chat(model:str):
    history = [{"role": "system", "content": system_promt},]
    while True:
        user_input = input("\nВы: ").strip()  

        if user_input.lower() in ["exit", "quit"]:
            print("Завершение сеанса...")
            break

        if not user_input:
            continue
        history.append({"role": "user", "content": user_input})
        try:
            answer_obj, usage = get_response(model=model, messages=history)

            is_quote_valid = (
                answer_obj.quote_found 
                and answer_obj.quote 
                and (answer_obj.quote.strip() in notes_data)
            )

            if is_quote_valid:
                final_output = f"📌 Цитата: {answer_obj.quote}\n💡 Ответ: {answer_obj.answer}"
            else:
                final_output = "В предоставленных заметках нет информации по этому вопросу."

            
            if usage is not None: 
                p = PRICES[model]
                input_tokens = getattr(usage, "input_tokens", 0) or 0
                output_tokens = getattr(usage, "output_tokens", 0) or 0
                details = getattr(usage, "input_tokens_details", None)
                cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
                fresh = input_tokens - cached
                cost = fresh * p["input"] + cached * p["cached"] + output_tokens * p["output"]
                _report(input_tokens=fresh, output_tokens=output_tokens,
                        cached=cached, cost=cost)
            else:
                print("[WARNING] Стрим завершился без события response.completed — usage неизвестен")

            history.append({"role": "assistant", "content": final_output})
            print(final_output)
        except openai.RateLimitError as e:
            print(f"\n[429 Rate Limit] Лимит запросов: {e.message}. Подождите и повторите.")
            history.pop()   # ← вот где вернулся твой откат «вопроса без ответа»
        except (openai.APIConnectionError, openai.APITimeoutError) as e:
            print(f"\n[Сеть/таймаут] Проблема с соединением к OpenAI: {e}")
            history.pop()
        except openai.APIError as e:
            print(f"\n[API Error OpenAI {e.status_code}] {e.message}")
            history.pop()
        except Exception as e:
            print(f"[Системная] {type(e).__name__}: {e}")
            history.pop()

def run_tests(model:str) -> list[dict]:
    results = []
    for t in TESTS:
        messages =[
            {"role": "system", "content": system_promt},
            {"role": "user", "content": t["q"]},  
        ]

        answer_obj, usage = get_response(model, messages) 
        ok, reason = check_expectations(answer_obj, t) 
        results.append({
                    "группа": t["group"], 
                    "вопрос": t["q"][:30] + "…",
                    "статус": "✅" if ok else "❌", 
                    "причина": reason
                })
    return results


def main():
    parser = argparse.ArgumentParser(description="CLI Chat SDK")
    
    parser.add_argument(
        "--model",
        choices=["gpt-4o", "gpt-4o-mini"],
        default="gpt-4o-mini",
        help="Выбор модели"
    )

    parser.add_argument(
        "--test",
        choices=["true", "false"],
        default=False,
        help="Прогнать тесты"
    )

    args = parser.parse_args()
    model = args.model
    test = args.test

    
    print(f"--- Чат запущен ({model} {f"Тест {test}" if test else ""}) ---")
   


    if test:
        print(run_tests(model=model))
    else:
        print("Команды: exit/quit")
        chat(model)

if __name__ == "__main__":
    main()
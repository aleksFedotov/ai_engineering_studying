from openai import OpenAI
from pydantic import BaseModel, Field, field_validator, ValidationError
from typing import Optional
from dotenv import load_dotenv, find_dotenv
import os

load_dotenv(find_dotenv())

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# --- Слой 1: модель для API (только форма) ---
class UserProfile(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None  # опциональность через union с null


# --- Слой 2: валидация значений в коде ---
class UserProfileValidated(UserProfile):
    name: str = Field(min_length=2, max_length=50)
    email: str = Field(pattern=r"^[\w.+-]+@[\w-]+\.[\w.]+$")

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v):
        if v is not None and not v.startswith("+"):
            raise ValueError("телефон должен начинаться с '+'")
        return v


def handle_structured_response(response):
    """Шаблон из гайда: 3 краевых случая ДО чтения output_parsed."""
    # 1. Обрыв по лимиту токенов
    if (response.status == "incomplete"
            and response.incomplete_details.reason == "max_output_tokens"):
        raise RuntimeError("Ответ оборван: увеличь max_output_tokens")
    # 2. Контент-фильтр
    if (response.status == "incomplete"
            and response.incomplete_details.reason == "content_filter"):
        raise RuntimeError("Генерация остановлена контент-фильтром")
    # 3. Refusal модели
    for item in response.output:
        if item.type != "message":
            continue
        for c in item.content:
            if c.type == "refusal":
                return {"ok": False, "refusal": c.refusal}
    if response.output_parsed is None:
        raise RuntimeError("Не удалось распарсить ответ")
    return {"ok": True, "data": response.output_parsed}


def main():
    response = client.responses.parse(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": "Извлеки профиль пользователя из текста."},
            {"role": "user", "content": "Меня зовут Alice, почта alice@example.com, телефон +79001234567."},
        ],
        text_format=UserProfile,  # <- модель без Field-ограничений
    )

    try:
        res = handle_structured_response(response)
        if not res["ok"]:
            print(f"Отказ модели: {res['refusal']}")
            return
        # Слой 2: валидация значений после успешного парсинга формы
        profile = UserProfileValidated.model_validate(res["data"].model_dump())
        print(f"Результат: {profile}")
    except ValidationError as e:
        # Форма соответствует схеме, но значения не прошли валидаторы
        print("Форма валидна, но значения нет:")
        for err in e.errors():
            print(f"  - {err['loc'][0]}: {err['msg']}")
    except RuntimeError as e:
        # Обрыв по max_output_tokens / контент-фильтр / не распарсилось
        print(f"Запрос не завершён: {e}")


if __name__ == "__main__":
    main()


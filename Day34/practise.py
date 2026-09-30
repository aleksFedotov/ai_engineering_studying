import instructor
from dotenv import load_dotenv, find_dotenv
from instructor.core import InstructorRetryException
from instructor.utils import disable_pydantic_error_url
import os       
from pydantic import BaseModel, field_validator,Field,EmailStr
from datetime import datetime, timezone,date
from typing import List
import re

load_dotenv(find_dotenv())
disable_pydantic_error_url()


client = instructor.from_provider("openai/gpt-4.1-mini")

client.on("completion:kwargs", lambda **kw: print(f"\n>>> ЗАПРОС К LLM, сообщений в истории: {len(kw['messages'])}"))

class UserDetails(BaseModel):
    name: str
    age: int

    @field_validator('name')
    @classmethod
    def name_must_be_uppercase(cls, v:str) -> str:
        if v.upper() != v:
            raise ValueError("Name must be in uppercase. Convert it")
        # Невыполнимый валидатор: имя должно содержать хотя бы один эмодзи
        # if not any(ord(char) > 0x1F600 for char in v):
        #     raise ValueError("Name MUST contain at least one emoji symbol.")
        # return v


# try:
#     user = client.create(
#         response_model=UserDetails,
#         max_retries=3, 
#         messages=[{"role": "user", "content": "Extract: jason is 25 years old"}],
#     )
#     print("\nРезультат:", user)

# except InstructorRetryException as e:
#     print("\n--- Сработал InstructorRetryException ---")
#     print(f"e.n_attempts: {e.n_attempts}")
#     print(f"Количество неудавшихся попыток (len(e.failed_attempts)): {len(e.failed_attempts)}")
#     print(f"Последнее исключение валидации: {e.last_completion}")



# class Event(BaseModel):
#     title: str
#     event_date: datetime = Field(description="Дата события, ISO 8601")

#     @field_validator("event_date")
#     @classmethod
#     def not_in_past(cls, v: datetime) -> datetime:
#         now = datetime.now(v.tzinfo) if v.tzinfo else datetime.now()
#         if v < now:
#             raise ValueError(
#                 f"event_date is in the past ({v.date()}). "
#                 f"Today's date is {date.today().isoformat()}. Pick a future date."
#             )
#         return v

# event = client.create(
#     response_model=Event,
#     max_retries=3,
#     messages=[{"role": "user", "content": "Запланируй встречу по возврату заказа на вчера, 15:00"}],
# )
# print("\nРезультат:", event)


def get_order_status(order_id: str) -> dict:
    assert re.match(r"^[A-Z]{3}-\d{5}$", order_id), "bad order_id"
    return {"order_id": order_id, "status": "in_transit", "eta_days": 3}

class CheckOrderStatusArgs(BaseModel):
    order_id: str = Field(..., description="ID заказа (формат: ABC-12345)")
    email: EmailStr

    @field_validator("order_id")
    def validate_order_id(cls, v : str) ->str:
        pattern = r"^[A-Z]{3}-\d{5}$"
        if not re.match(pattern, v):
            raise ValueError("order_id must strictly match format ABC-12345")
        return v


user_query = "Где мой заказ ABC-12345?"

controller_args = client.create(
    response_model=CheckOrderStatusArgs,
    max_retries=3,
    messages=[
        {
            "role": "system",
            "content": "Ты — контроллер. Извлеки order_id из обращения пользователя.",
        },
        {"role": "user", "content": user_query},
    ],
)
print(">>> [Controller Output]:", controller_args)


status_dict = get_order_status(controller_args.order_id)
print(">>> [Python Execution (БД/API)]:", status_dict)

class UIResponse(BaseModel):
    greeting: str = Field(description="Приветствие клиента")
    status_text: str = Field(
        description="Понятный текст о статусе заказа и сроках доставки"
    )
    next_steps: List[str] = Field(
        description="Список предложенных шагов для пользователя"
    )

formatter_response = client.create(
    response_model=UIResponse,
    max_retries=3,
    messages=[
        {
            "role": "user",
            "content": (
                f"Клиент спрашивал: '{user_query}'\n"
                f"Данные из системы: {status_dict}\n"
                f"Сформируй ответ для UI."
            ),
        }
    ],
)

print("\n=== Итоговый UIResponse (JSON) ===")
print(formatter_response.model_dump_json(indent=2))
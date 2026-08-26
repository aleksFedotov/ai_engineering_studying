from typing import List, Literal

from openai import OpenAI
from pydantic import BaseModel,Field,ValidationError
import os
from dotenv import load_dotenv

load_dotenv("../.env")


client  = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class WorkExperience(BaseModel):
    
    company: str = Field(description="Название компании")
    position: str = Field(description="Должность")
    start_year: int = Field(description="Год начала работы")
    end_year: int | None = Field(
        description="Год окончания работы, null если работает по настоящее время"
    )
    technologies: list[str] = Field(
        description="Список технологий и инструментов; пустой список, если не указаны"
    )


class Education(BaseModel):
   
    institution: str = Field(description="Название учебного заведения")
    degree: str | None = Field(
        description="Специальность/направление, null если не указано"
    )
    graduation_year: int | None = Field(
        description="Год окончания, null если не указан"
    )

class Resume(BaseModel):
    full_name: str | None
    age: int | None
    email: str | None
    phone: str | None
    work_experience:List[WorkExperience]
    education:List[Education]
    english_level: Literal["A1", "A2", "B1", "B2", "C1", "C2", "native"] | None
    salary_expectation_rub: int | None
    remote_only: bool


resume_text = """
Иван Петров, 28 лет. Email: ivan.petrov@gmail.com, телефон +7-915-123-45-67.

Опыт работы:
— Яндекс, backend-разработчик, 2021–2024. Работал с Python, PostgreSQL, Redis,
  развивал сервис рекомендаций, ускорил ответ API на 40%.
— TechFlow, junior-разработчик, 2019–2021. Писал на Python и JavaScript,
  поддерживал внутреннюю CRM.

Образование:
— МГУ им. Ломоносова, прикладная математика, выпуск 2019.

Английский — B2 (читаю документацию, свободно переписываюсь).

Ищу только удалённую работу. Зарплатные ожидания — от 250 000 руб.
"""

resume_text_minimal = """
Мария Сидорова, 30 лет. Работаю аналитиком данных в Сбере с 2020 года.
Закончила ВШЭ в 2018. Готова к офису или гибриду.
"""

resume_text_not_resume = """
Рецепт борща: сварить бульон из свинины, добавить свёклу, капусту,
картофель и морковь. Варить 40 минут, подавать со сметаной.
"""



def parse_resume(text:str,tokens:int) -> Resume | None:
    try:
        response = client.responses.parse(
            model='gpt-5.6',
            input=[
                {
                    "role": "system",
                    "content": (
                        "Извлеки данные из резюме. Если какого-то поля нет в тексте — "
                        "верни null (или пустой список). Не выдумывай значения."
                    ),
                },
                {"role": "user", "content": text},
            ],

            text_format=Resume,
            max_output_tokens=tokens
        ) 
        if response.status ==  "incomplete":
            reason = response.incomplete_details.reason if response.incomplete_details else "unknown"
            print(f"Ответ неполный, причина: {reason}")
            return None        


        for output in response.output:
            if output.type != "message":
                continue

            for item in output.content:
                if item.type == "refusal":
                    print(f"Отказ: {item.refusal}")
                    return None

                if not item.parsed:
                        raise Exception("Could not parse response")
            return  response.output_parsed

    except ValidationError:
        print("Ответ не удалось распарсить (вероятно, обрезан по токенам)")
        return None

def main():
    for name, text, tokens in [
        ("Полное резюме", resume_text, 2048),
        ("Минимальное резюме", resume_text_minimal,2048),
        ("Не резюме", resume_text_not_resume,2048),
        ("Мало токенов", resume_text_not_resume,32),
    ]:
        print(f"--- {name} ---")
        resume = parse_resume(text,tokens)
        if resume is None:
            print("Модель отказалась или не смогла ответить")
        else:
            print(resume.model_dump_json(indent=2, ensure_ascii=False))



if __name__ == "__main__":
    main()
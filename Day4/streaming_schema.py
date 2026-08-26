from typing import List

from openai import OpenAI
from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv("../.env")


client  = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class EntitiesModel(BaseModel):
    attributes: List[str]
    colors: List[str]
    animals: List[str]


with client.responses.stream(
    model="gpt-5.6",
    input=[
        {"role": "system", "content": "Extract entities from the input text"},
        {
            "role": "user",
            "content": "The quick brown fox jumps over the lazy dog with piercing blue eyes",
        },
    ],
    text_format= EntitiesModel
    
) as stream:
    for event in stream:
        event_type= getattr(event, "type", None)
        if event.type == "response.refusal.delta":
            print(event.delta, end="")
        elif event.type == "response.output_text.delta":
            print(event.delta, end="")
        elif event.type == "response.error":
            print(event.error, end="")
        elif event.type == "response.completed":
            print("Completed")

    final_response = stream.get_final_response()
    print(final_response)
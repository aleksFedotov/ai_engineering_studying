from openai import OpenAI
from typing import List
from enum import Enum
from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv('../.env')

client =  OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class UIType(str,Enum):
    div = "div"
    button = "button"
    header = "header"
    section = "section"
    field = "field"
    form = "form"

class Attribute(BaseModel):
    name:str 
    value:str

class UI(BaseModel):
    type: UIType
    label: str
    children: List["UI"]
    attributes: List[Attribute]


UI.model_rebuild()

class Response(BaseModel):
    ui: UI


response = client.responses.parse(
    model="gpt-5.6",
    input = [
    {
        "role" : "system",
        "content" : "You are a UI generator AI. Convert the user input into a UI",
    },
    {"role" : "user", "content" : "Make a User Profile Form"}
    ],
    text_format=Response
)

ui = response.output_parsed

print(ui)

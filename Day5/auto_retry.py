from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv("../.env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), max_retries=0)


response = client.with_options(max_retries=5).responses.create(
    model="gpt-5.6",
    messages=[{"role": "user", "content": "hi"}],
)
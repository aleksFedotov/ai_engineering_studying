import os
import requests
from dotenv import load_dotenv

load_dotenv("../.env")

r = requests.get(
    "https://openrouter.ai/api/v1/models",
    headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"},
)
models = r.json()["data"]

free = [m["id"] for m in models if m["id"].endswith(":free")]
print(f"Доступно free-моделей: {len(free)}")
for m in free[:20]:
    print(m)
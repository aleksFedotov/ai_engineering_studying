from openai import OpenAI
from anthropic import Anthropic
from dotenv import load_dotenv
import os

load_dotenv("../.env")
open_api_key = os.getenv("OPENAI_API_KEY") 
claude_API_KEY =os.getenv("CLAUDE_API_KEY")

clientOpenAI = OpenAI(api_key=os.getenv("OPENAI_API_KEY") )
clientClaude = Anthropic(api_key=os.getenv("CLAUDE_API_KEY") )

response = clientOpenAI.responses.create(
  
    model="gpt-4.1-mini",
    input="What is the capital of Germany?"
)

message = clientClaude.messages.create(
    model="claude-opus-5",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "What is the capital of France?"}
    ]
)

print(response.output_text)

for block in message.content:
    if block.type  == "text":
        print(block.text)

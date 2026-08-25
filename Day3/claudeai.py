import json
import logging
import os
from typing import AsyncGenerator, Dict, Any
from fastapi  import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import anthropic
import uvicorn



load_dotenv("../.env")



client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))


with client.messages.stream(
    model= "claude-opus-5",
    messages=[{"role": "user", "content": "Hello"}],
    max_tokens=1024,
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush="true")
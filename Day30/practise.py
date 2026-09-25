import json
import os

import requests
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

tools = [
    {
        "type": "function",
        "name": "get_weather",
        "description": (
            "Get the current weather for a city. "
            "Returns city, country, temperature, weather code, "
            "humidity and wind speed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name, for example: Berlin",
                }
            },
            "required": ["city"],
            "additionalProperties": False,
        },
        "strict": True,
    }
]


def get_weather(city: str) -> dict:
    geo_response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": "en"},
        timeout=10,
    )
    geo_response.raise_for_status()
    geo_data = geo_response.json()

    if not geo_data.get("results"):
        raise ValueError(f"City not found: {city}")

    place = geo_data["results"][0]

    weather_response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": (
                "temperature_2m,relative_humidity_2m,"
                "weather_code,wind_speed_10m"
            ),
            "timezone": "auto",
        },
        timeout=10,
    )
    weather_response.raise_for_status()
    current = weather_response.json()["current"]

    return {
        "city": place["name"],
        "country": place.get("country"),
        "temperature_c": current["temperature_2m"],
        "humidity_percent": current["relative_humidity_2m"],
        "weather_code": current["weather_code"],
        "wind_speed_kmh": current["wind_speed_10m"],
    }


input_list = [
    {
        "role": "user",
        "content": "What is the current weather in Berlin?",
    }
]

first_response = client.responses.create(
    model="gpt-4o-mini",
    tools=tools,
    input=input_list,
    tool_choice="auto",
    parallel_tool_calls=False,
)

call = next(
    item for item in first_response.output
    if item.type == "function_call"
)

print("\n=== RAW FUNCTION CALL ===")
print(json.dumps(call.model_dump(), indent=2, ensure_ascii=False))

# Сохраняем вызов модели в историю.
input_list += first_response.output

arguments = json.loads(call.arguments)

try:
    weather = get_weather(arguments["city"])
    tool_output = json.dumps(weather, ensure_ascii=False)
except Exception as exc:
    tool_output = json.dumps(
        {"error": str(exc)},
        ensure_ascii=False,
    )

print("\n=== FUNCTION OUTPUT ===")
print(tool_output)


if os.getenv("RETURN_TOOL_RESULT", "1") == "0":
    print("\nStopped before returning the tool result to the model.")
    raise SystemExit

input_list.append(
    {
        "type": "function_call_output",
        "call_id": call.call_id,
        "output": tool_output,
    }
)

second_response = client.responses.create(
    model="gpt-4o-mini",
    tools=tools,
    input=input_list,
)

print("\n=== FINAL ANSWER ===")
print(second_response.output_text)
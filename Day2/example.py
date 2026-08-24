from openai import OpenAI
from anthropic import Anthropic 
from dotenv import load_dotenv
import os

load_dotenv("../.env")

clientOpenAI = OpenAI(api_key = os.getenv("OPENAI_API_KEY"))
clientClaude = Anthropic(api_key= os.getenv("CLAUDE_API_KEY"))


# clauseMessage = clientClaude.messages.create(
#     model="claude-opus-5",
#     max_tokens=1024,
#     messages=[
#         {"role": "user", "content": "Hello, Claude"},
#         {"role": "assistant", "content": "Hello!"},
#         {"role": "user", "content": "Can you describe LLMs to me?"},
#     ],
# )

# print(clauseMessage)

prompt = "Придумай метафору, описывающую работу оперативной памяти (ОЗУ) компьютера."
temperatures = [0.0, 0.7, 1.5]
runs_per_temp = 3

for temp in temperatures:
    print(f"\n================ TEMPERATURE: {temp} ================")
    for i in range(1, runs_per_temp + 1):
        response = clientOpenAI.chat.completions.create(
            model="gpt-4o-mini",
            temperature=temp,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content.strip()
        print(f"\n[Прогон {i}]:\n{text}")

# second_response = clientOpenAI.responses.create(
#     model = 'o3-mini',
#     previous_response_id= response.id,
#     input =[{'role':'user', 'content':'explain why this is funny'}]
# )

# print(second_response.output_text)


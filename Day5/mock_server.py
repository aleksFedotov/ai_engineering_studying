# mock_server.py — запустить отдельно: python mock_server.py
from aiohttp import web

counter = 0

async def handle(request):
    global counter
    counter += 1
    if counter % 3 != 0: 
        return web.json_response(
            {"error": {"message": "Rate limit reached", "type": "rate_limit_error"}},
            status=429,
            headers={"Retry-After": "2", "x-request-id": f"req_mock_{counter}"},
        )
    return web.json_response({
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "model": "mock",
    }, headers={"x-request-id": f"req_mock_{counter}"})

app = web.Application()
app.router.add_post("/v1/chat/completions", handle)
web.run_app(app, port=8899)


from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Route
from starlette.middleware.cors import CORSMiddleware
import json
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key="your-api-key")

SYSTEM_PROMPT = "你是一个专业、友善的 AI 助手，请用简洁清晰的中文回答用户的问题。"


async def chat_stream(request: Request):
    """
    请求体格式：
    {
        "history": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮助你的？"}
        ],
        "message": "今天天气怎么样？"
    }
    """
    body = await request.json()
    history: list = body.get("history", [])
    user_message: str = body.get("message", "")

    if not user_message.strip():
        async def error_gen():
            yield "data: " + json.dumps({"error": "message 不能为空"}, ensure_ascii=False) + "\n\n"

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    # 组装完整消息列表：系统提示 + 历史 + 本次提问
    messages = (
            [{"role": "system", "content": SYSTEM_PROMPT}]
            + history
            + [{"role": "user", "content": user_message}]
    )

    async def event_generator():
        try:
            stream = await client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                if delta.content:
                    data = json.dumps({"content": delta.content}, ensure_ascii=False)
                    yield f"data: {data}\n\n"

                if finish_reason == "stop":
                    yield "data: [DONE]\n\n"

        except Exception as e:
            err = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，确保实时推送
        },
    )


app = Starlette(
    routes=[
        Route("/chat/stream", chat_stream, methods=["POST"]),
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

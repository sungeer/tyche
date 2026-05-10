from starlette.responses import StreamingResponse

from src.core.exceptions import BadRequestError
from src.agents.game import service
from src.utils import serial, rand


async def chat(request):
    data = await request.json()  # dict

    session_id = data.get('session_id') or rand.gen_token()
    user_input = (data.get('user_input') or '').strip()

    if not user_input:
        raise BadRequestError('user_input 不能为空')

    user_id = request.user.user_id

    async def event_generator():
        async for token in service.chat_stream(session_id, user_id, user_input):
            yield serial.to_json({'text': token}) + '\n'

    headers = {
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',  # 关闭 Nginx 缓冲
    }

    return StreamingResponse(event_generator(), media_type='application/x-ndjson', headers=headers)

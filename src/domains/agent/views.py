import asyncio
import json

from loguru import logger
from starlette.responses import StreamingResponse

from src.core.exceptions import BadRequestError
from src.core.response import ok
from src.domains.agent import service, pipeline
from src.domains.agent.state import make_initial_state
from src.core.auth import login_required, permission_required
from src.utils import serial


async def chat(request):
    data = await request.json()  # dict
    message = (data.get('message') or '').strip()
    session_id = data.get('session_id') or ''

    if not message:
        raise BadRequestError('message 不能为空')

    user = request.user

    # 加载或创建会话 获取历史消息
    session, history = await service.load_or_create_session(user.user_id, session_id)

    # 构建初始 AgentState
    state = make_initial_state(message=message, user=user, session=session, history=history)

    async def event_generator():
        full_text = ''

        async for token in service.chat_stream(state):
            full_text += token
            yield serial.to_json({'text': token}) + '\n'

        # 流结束后保存本轮消息
        try:
            await service.save_turn_messages(
                session_id=state['input']['session_id'],
                turn_id=state['input']['turn_id'],
                user_message=message,
                assistant_response=full_text,
            )
        except Exception as e:
            logger.error(f'[chat] 消息保存失败：{e}')

    headers = {
        'X-Run-Id': state['input']['run_id'],
        'X-Turn-Id': state['input']['turn_id'],
        'X-Session-Id': state['input']['session_id'],
        'Cache-Control': 'no-cache',
    }

    return StreamingResponse(event_generator(), media_type='application/x-ndjson', headers=headers)

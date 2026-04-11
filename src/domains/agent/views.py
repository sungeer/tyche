"""
Agent HTTP 端点（全部使用 POST）
/agent.chat           POST  多轮对话（SSE 流式）
/agent.task.status    POST  查询任务状态
/agent.review.list    POST  查看待审核任务（审核人用）
/agent.review.approve POST  审核通过
/agent.review.reject  POST  审核驳回
/agent.session.clear  POST  清除会话上下文
/agent.metrics        POST  系统指标（仅 ADMIN）
"""
import asyncio
import json

from loguru import logger
from starlette.responses import StreamingResponse

from src.core.exceptions import BadRequestError
from src.core.response import ok
from src.domains.agent import service, pipeline
from src.domains.agent.state import make_initial_state
from src.core.auth import login_required
from src.utils import serial


# 多轮对话 SSE 流式
@login_required
async def chat(request):
    """
    多轮对话接口 SSE 流式
    1. 解析请求
    2. 加载/创建会话
    3. 构建初始 AgentState
    4. 将 Pipeline 作为后台任务运行
    5. 通过 StreamingResponse + asyncio.Queue 流式返回 SSE
    """
    body = serial.from_json(await request.body())
    message = (body.get('message') or '').strip()
    session_id = body.get('session_id') or ''

    if not message:
        raise BadRequestError('message 不能为空')

    user = request.user

    # 加载或创建会话，获取历史消息
    session, history = await service.load_or_create_session(user.user_id, session_id)

    # 构建初始 AgentState
    state = make_initial_state(message=message, user=user, session=session, history=history)

    # SSE token 队列：Pipeline 向此推送事件，event_generator 读取并返回
    token_queue = asyncio.Queue()
    state['_sse_queue'] = token_queue

    # Pipeline 作为后台任务并发运行
    async def run_pipeline_and_save():
        completed_state = await pipeline.run(state)
        # Pipeline 完成后，异步保存本轮消息
        try:
            response = completed_state['working'].get('response')
            assistant_text = response['text'] if response else None
            await service.save_turn_messages(
                session_id=completed_state['input']['session_id'],
                turn_id=completed_state['input']['turn_id'],
                user_message=message,
                assistant_response=assistant_text,
            )
        except Exception as e:
            logger.error(f'[chat] 消息保存失败：{e}')

    asyncio.create_task(run_pipeline_and_save())

    # SSE event generator
    async def event_generator():
        while True:
            event = await token_queue.get()
            if event is None:
                break
            yield f'event: {event["event"]}\ndata: {json.dumps(event["data"], ensure_ascii=False)}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'X-Run-Id': state['input']['run_id'],
            'X-Turn-Id': state['input']['turn_id'],
            'X-Session-Id': state['input']['session_id'],
            'Cache-Control': 'no-cache',
        },
    )


# 查询任务状态
@login_required
async def task_status(request):
    """查询任务状态
    用于轮询人工审核结果
    """
    body = serial.from_json(await request.body())
    task_id = (body.get('task_id') or '').strip()
    if not task_id:
        raise BadRequestError('task_id 不能为空')

    result = await service.get_task_status(task_id)
    return ok(result)


@login_required
async def review_list(request):
    """查询当前用户角色的待审核任务列表"""
    tasks = await service.get_review_list(request.user.roles)
    return ok({'tasks': tasks, 'total': len(tasks)})


@login_required
async def review_approve(request):
    """审核通过"""
    user = request.user

    body = serial.from_json(await request.body())
    task_id = (body.get('task_id') or '').strip()
    note = (body.get('note') or '').strip()

    if not task_id:
        raise BadRequestError('task_id 不能为空')

    state = await service.process_review_decision(
        task_id=task_id,
        reviewer_id=user.user_id,
        decision='approved',
        reviewer_note=note,
    )

    return ok({
        'task_id': task_id,
        'status': state['control']['status'],
        'message': '审核已通过，流程已恢复执行',
    })


@login_required
async def review_reject(request):
    """审核驳回"""
    user = request.user

    body = serial.from_json(await request.body())
    task_id = (body.get('task_id') or '').strip()
    note = (body.get('note') or '').strip()

    if not task_id:
        raise BadRequestError('task_id 不能为空')
    if not note:
        raise BadRequestError('驳回原因不能为空')

    await service.process_review_decision(
        task_id=task_id,
        reviewer_id=user.user_id,
        decision='rejected',
        reviewer_note=note,
    )

    return ok({'task_id': task_id, 'message': '审核已驳回，申请人将收到通知'})


@login_required
async def session_clear(request):
    """用户主动清除会话上下文"""
    user = request.user

    body = serial.from_json(await request.body())
    session_id = (body.get('session_id') or '').strip()
    if not session_id:
        raise BadRequestError('session_id 不能为空')

    await service.clear_session(user.user_id, session_id)
    return ok({'message': '会话上下文已清除，下次对话将开启新会话'})


@login_required
async def metrics(request):
    """
    系统指标接口（仅 skill:manage 权限）。
    返回近 24h 各节点 P95 耗时、错误率、Skill 调用分布。
    """
    data = await service.get_metrics(request.user.roles, since_hours=24)
    return ok(data)

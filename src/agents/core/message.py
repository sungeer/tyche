"""Agent 消息系统
定义 框架内 统一 的 消息格式
确保 智能体 与模型之间 信息传递的 标准化
"""

from datetime import datetime

# OpenAI API 规范
valid_roles = ('user', 'assistant', 'system', 'tool')


# 消息类
class Message:

    def __init__(self, content, role, timestamp=None, metadata=None):
        if not isinstance(content, str):
            raise TypeError(f'content 必须是 str，而不是 {type(content).__name__}')
        if not content:
            raise ValueError('content 不能为空字符串')

        if role not in valid_roles:
            raise ValueError(f'role 必须是 {valid_roles} 之一，而不是 {role!r}')

        if timestamp is not None and not isinstance(timestamp, datetime):
            raise TypeError(f'timestamp 必须是 datetime，而不是 {type(timestamp).__name__}')

        if metadata is not None and not isinstance(metadata, dict):
            raise TypeError(f'metadata 必须是 dict，而不是 {type(metadata).__name__}')

        self.content = content
        self.role = role
        self.timestamp = timestamp if timestamp is not None else datetime.now()  # 用于日志记录
        self.metadata = metadata if metadata is not None else {}  # 预留的功能扩展

    def to_dict(self):
        """转换为字典格式
        OpenAI API 格式
        """
        return {
            'role': self.role,
            'content': self.content,
        }

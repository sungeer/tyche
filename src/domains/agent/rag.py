"""
知识库（RAG）检索封装
基于 ChromaDB 向量数据库，与业务 Skill 并发执行于 Node3 阶段。
"""
from loguru import logger

from src.core.config import settings
from src.core.executor import bio_threadpool
from src.utils.concurrency import run_in_threadpool

# ChromaDB 集合名称 → 所需权限
_COLLECTION_PERMISSION_MAP = {
    'product_prospectus':   'product:read',
    'regulatory_documents': 'audit:read',
    'investment_research':  'risk:read',
    'private_banking_docs': 'portfolio:read_all',
}

# 延迟初始化 ChromaDB 客户端，避免应用启动时 ChromaDB 不可用
_chroma_client = None


def _get_client():
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        _chroma_client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
    return _chroma_client


def _get_allowed_collections(user_roles):
    """根据用户角色，返回有权检索的集合名称列表"""
    return [
        name
        for name, required_perm in _COLLECTION_PERMISSION_MAP.items()
        if required_perm in user_roles
    ]


def _build_rag_query(message, entities, intent_category):
    """
    拼接检索 query：原始问题 + 意图关键词 + 实体名称。
    比纯用户输入更精准，减少无关文档的干扰。
    """
    parts = [message]
    if intent_category:
        parts.append(intent_category)
    if entities:
        for v in entities.values():
            if isinstance(v, str):
                parts.append(v)
    return ' '.join(parts)


def _query_sync(user_roles, message, entities, intent_category):
    """同步 ChromaDB 检索，返回 knowledge_chunks 列表"""
    client = _get_client()
    query = _build_rag_query(message, entities, intent_category)
    allowed_collections = _get_allowed_collections(user_roles)

    chunks = []
    for collection_name in allowed_collections:
        try:
            collection = client.get_collection(collection_name)
            results = collection.query(
                query_texts=[query],
                n_results=3,
                where={'expired': False},
            )
            for i, doc in enumerate(results['documents'][0]):
                score = 0.0
                if results.get('distances') and results['distances'][0]:
                    # ChromaDB 距离转相似度：1 - 归一化距离
                    score = max(0.0, 1 - results['distances'][0][i])
                chunks.append({
                    'doc_id': results['ids'][0][i],
                    'content': doc,
                    'score': score,
                    'metadata': results['metadatas'][0][i] if results.get('metadatas') else {},
                })
        except Exception as e:
            logger.warning(f'[RAG] 集合 {collection_name} 检索失败：{e}')

    # 按相似度降序，取 top-5
    chunks.sort(key=lambda x: x['score'], reverse=True)
    return chunks[:5]


async def retrieve(state):
    """
    在 bio_threadpool 中执行 ChromaDB 检索，返回 knowledge_chunks 列表。
    Node3 阶段与业务 Skill 并发调用。
    """
    user_roles = state['input']['user']['roles']
    intent = state['working']['intent']
    message = state['input']['message']
    entities = intent.get('entities', {}) if intent else {}
    intent_category = intent.get('category', '') if intent else ''

    return await run_in_threadpool(
        bio_threadpool,
        _query_sync,
        user_roles,
        message,
        entities,
        intent_category,
    )

# rag_demo.py

import asyncio
from contextlib import asynccontextmanager

import chromadb
from sentence_transformers import SentenceTransformer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


# ============================================================
# 1. RAG 服务
# ============================================================

class RAGService:
    def __init__(self, db_path: str = "./chroma_db", model_name: str = "BAAI/bge-small-zh-v1.5"):
        # 本地持久化向量库（首次运行会在当前目录创建 chroma_db 文件夹）
        self.client = chromadb.PersistentClient(path=db_path)

        # 获取或创建 collection，metadata 指定用余弦相似度
        self.collection = self.client.get_or_create_collection(
            name="knowledge_base",
            metadata={"hnsw:space": "cosine"}
        )

        # 本地 Embedding 模型（首次运行会自动下载，中文效果好）
        # 也可以换成你自己部署的 embedding 服务
        print("正在加载 Embedding 模型...")
        self.embed_model = SentenceTransformer(model_name)
        print("Embedding 模型加载完成")

    # ── 同步方法（供 to_thread 调用）──────────────────────────

    def _embed(self, text: str) -> list:
        """文本 → 向量"""
        return self.embed_model.encode(text, normalize_embeddings=True).tolist()

    def _sync_add_documents(self, docs: list[dict]):
        """
        批量写入文档
        docs 格式：[{"id": "唯一id", "content": "文档内容", "metadata": {...}}]
        用 upsert：id 已存在则更新，不存在则插入
        """
        self.collection.upsert(
            ids=[d["id"] for d in docs],
            documents=[d["content"] for d in docs],
            embeddings=[self._embed(d["content"]) for d in docs],
            metadatas=[d.get("metadata", {}) for d in docs],
        )

    def _sync_retrieve(self, query: str, top_k: int = 5, score_threshold: float = 0.5) -> list[dict]:
        """
        检索最相关文档
        ChromaDB 使用余弦距离（distance），范围 [0, 2]，越小越相关
        换算成相似度 score = 1 - distance，范围 [-1, 1]
        """
        # 知识库为空时直接返回
        if self.collection.count() == 0:
            return []

        query_embedding = self._embed(query)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.collection.count()),  # 防止 top_k 超过文档总数
            include=["documents", "metadatas", "distances"]
        )

        docs = []
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i]
            score = 1 - distance  # 转换为相似度

            docs.append({
                "id": doc_id,
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "score": round(score, 4),
            })

        # 按相似度过滤，低于阈值的视为"无相关内容"
        filtered = [d for d in docs if d["score"] >= score_threshold]

        # 按 score 降序排列
        filtered.sort(key=lambda x: x["score"], reverse=True)
        return filtered

    # ── 异步方法（Starlette 协程调用这里）───────────────────────

    async def add_documents(self, docs: list[dict]):
        """异步写入文档，用 to_thread 避免阻塞事件循环"""
        await asyncio.to_thread(self._sync_add_documents, docs)

    async def retrieve(self, query: str, top_k: int = 5, score_threshold: float = 0.5) -> list[dict]:
        """异步检索"""
        return await asyncio.to_thread(self._sync_retrieve, query, top_k, score_threshold)

    async def delete_document(self, doc_id: str):
        """异步删除单个文档"""
        await asyncio.to_thread(self.collection.delete, ids=[doc_id])

    async def count(self) -> int:
        """当前知识库文档总数"""
        return self.collection.count()


# ============================================================
# 2. 预置测试数据
# ============================================================

SAMPLE_DOCS = [
    {
        "id": "doc_001",
        "content": "Python 是一种解释型、高级、通用的编程语言，由吉多·范罗苏姆于1991年创建，以代码简洁易读著称。",
        "metadata": {"category": "编程语言", "source": "wiki"}
    },
    {
        "id": "doc_002",
        "content": "ChromaDB 是一个开源的向量数据库，支持本地部署，常用于 RAG（检索增强生成）应用场景。",
        "metadata": {"category": "数据库", "source": "官方文档"}
    },
    {
        "id": "doc_003",
        "content": "RAG（Retrieval-Augmented Generation）通过在生成前先检索相关文档，有效减少大语言模型的幻觉问题。",
        "metadata": {"category": "AI技术", "source": "论文"}
    },
    {
        "id": "doc_004",
        "content": "Starlette 是一个轻量级的 Python 异步 Web 框架，基于 ASGI 协议，FastAPI 就是基于它构建的。",
        "metadata": {"category": "Web框架", "source": "官方文档"}
    },
    {
        "id": "doc_005",
        "content": "向量数据库通过将文本转换为高维向量，利用近似最近邻（ANN）算法实现语义相似度搜索。",
        "metadata": {"category": "AI技术", "source": "技术博客"}
    },
]

# ============================================================
# 3. Starlette 应用
# ============================================================

rag_service = RAGService()


@asynccontextmanager
async def lifespan(app):
    # 启动时写入测试数据
    print("正在写入测试文档...")
    await rag_service.add_documents(SAMPLE_DOCS)
    count = await rag_service.count()
    print(f"知识库已就绪，共 {count} 条文档")
    yield
    # 关闭时的清理逻辑（如有需要）


async def query_endpoint(request: Request):
    """
    POST /query
    Body: {"question": "xxx", "top_k": 3, "score_threshold": 0.5}
    """
    body = await request.json()
    question = body.get("question", "").strip()

    if not question:
        return JSONResponse({"error": "question 不能为空"}, status_code=400)

    top_k = int(body.get("top_k", 3))
    score_threshold = float(body.get("score_threshold", 0.5))

    docs = await rag_service.retrieve(question, top_k=top_k, score_threshold=score_threshold)

    return JSONResponse({
        "question": question,
        "has_result": len(docs) > 0,
        "count": len(docs),
        "docs": docs,
    })


async def add_endpoint(request: Request):
    """
    POST /add
    Body: {"docs": [{"id": "...", "content": "...", "metadata": {...}}]}
    """
    body = await request.json()
    docs = body.get("docs", [])

    if not docs:
        return JSONResponse({"error": "docs 不能为空"}, status_code=400)

    await rag_service.add_documents(docs)
    return JSONResponse({"message": f"成功写入 {len(docs)} 条文档"})


async def delete_endpoint(request: Request):
    """
    DELETE /delete/{doc_id}
    """
    doc_id = request.path_params["doc_id"]
    await rag_service.delete_document(doc_id)
    return JSONResponse({"message": f"已删除文档 {doc_id}"})


async def stats_endpoint(request: Request):
    """GET /stats — 查看知识库状态"""
    count = await rag_service.count()
    return JSONResponse({"total_docs": count})


app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/query", query_endpoint, methods=["POST"]),
        Route("/add", add_endpoint, methods=["POST"]),
        Route("/delete/{doc_id}", delete_endpoint, methods=["DELETE"]),
        Route("/stats", stats_endpoint, methods=["GET"]),
    ]
)

from openai import OpenAI
from pymilvus import connections, Collection

# ==========================================
# 0. 准备工作：初始化客户端
# ==========================================
# 假设你的 base_url 和 api_key 已经配置好
client = OpenAI(
    api_key="your-api-key",
    base_url="your-base-url"
)  # wx AsyncOpenAI

# 连接到你的 Milvus 数据库 (假设是本地)
connections.connect(host='localhost', port='19530')

# 获取你之前建好的宪法集合
collection = Collection("constitution_collection")
# 加载集合到内存中（如果没加载的话无法搜索）
collection.load()

# ==========================================
# 1. 向量化用户的问题
# ==========================================
user_question = "我国的宪法第一条是什么"
print(f"用户问题: {user_question}\n")

# 调用 embeddings.create 把问题变成向量
# 注意：这里的 model 必须和你存入 Milvus 时使用的模型保持完全一致！
embeddings = client.embeddings.create(
    model="text-embedding-3-small",  # 替换成你用的模型
    input=user_question
)

question_embedding = [data.embedding for data in embeddings.data]

# ==========================================
# 2. 去 Milvus 中检索相似的文本
# ==========================================
# 在 Milvus 中进行向量相似度搜索
# 假设你存向量字段名叫 "vector"，存原始文本的字段名叫 "text"
search_params = {
    "metric_type": "COSINE",  # 向量相似度计算方式
    "params": {"nprobe": 10}  # 搜索范围控制参数
}

search_results = collection.search(
    data=question_embedding,  # 传入问题的向量
    anns_field="vector",  # 在哪个字段里搜
    param=search_params,
    limit=3,  # 只取最相关的 3 条结果
    output_fields=["text"]  # 搜索结果要返回原始文本内容
)  # wx to_thread_pool

# 提取搜索到的文本内容
retrieved_texts = []
for hits in search_results:
    for hit in hits:
        retrieved_texts.append(hit.entity.get("text"))

print(f"检索到的相关宪法条文:\n{'-' * 30}")
for i, text in enumerate(retrieved_texts):
    print(f"{i + 1}. {text}\n")

# ==========================================
# 3. 构建 Prompt (提示词)
# ==========================================
# 把找到的背景知识和用户问题拼起来
context_str = "\n".join([f"{i + 1}. {t}" for i, t in enumerate(retrieved_texts)])

prompt = f"""
你是一个严谨的法律助手。请仅仅根据以下提供的【参考资料】来回答用户的【问题】。
如果参考资料中没有包含答案，请回答“根据提供的资料无法回答”。
不要自己编造信息。

【参考资料】：
{context_str}

【问题】：{user_question}

【回答】：
"""

# ==========================================
# 4. 调用大模型生成最终答案
# ==========================================
response = client.chat.completions.create(
    model="gpt-4o-mini",  # 替换成你用来聊天的模型
    messages=[
        {"role": "user", "content": prompt}
    ],
    temperature=0.1  # 设低一点，让回答更严谨，减少幻觉
)

final_answer = response.choices[0].message.content
print(f"最终回答:\n{'-' * 30}\n{final_answer}")

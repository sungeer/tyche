import asyncio
from openai import AsyncOpenAI
from pymilvus import connections, Collection

client = AsyncOpenAI(
    api_key="your-api-key",
    base_url="your-base-url"
)


async def main():
    connections.connect(host='localhost', port='19530')
    collection = Collection("constitution_collection")
    collection.load()

    user_question = "我国的宪法第一条是什么"
    print(f"用户问题: {user_question}\n")

    try:
        # ✅ await 异步调用 embedding
        embeddings = await client.embeddings.create(
            model="text-embedding-3-small",
            input=user_question
        )
        question_embedding = [data.embedding for data in embeddings.data]

        # ✅ Milvus 是同步库，用 run_in_executor 丢到线程池，避免阻塞事件循环
        loop = asyncio.get_running_loop()
        search_params = {
            "metric_type": "COSINE",
            "params": {"nprobe": 10}
        }
        search_results = await loop.run_in_executor(
            None,  # 使用默认线程池
            lambda: collection.search(
                data=question_embedding,
                anns_field="vector",
                param=search_params,
                limit=3,
                output_fields=["text"]
            )
        )

        retrieved_texts = []
        for hits in search_results:
            for hit in hits:
                retrieved_texts.append(hit.entity.get("text"))

        print(f"检索到的相关宪法条文:\n{'-' * 30}")
        for i, text in enumerate(retrieved_texts):
            print(f"{i + 1}. {text}\n")

        context_str = "\n".join([f"{i + 1}. {t}" for i, t in enumerate(retrieved_texts)])

        prompt = f"""\
你是一个严谨的法律助手。请仅仅根据以下提供的【参考资料】来回答用户的【问题】。
如果参考资料中没有包含答案，请回答"根据提供的资料无法回答"。
不要自己编造信息。

【参考资料】：
{context_str}

【问题】：{user_question}

【回答】：
"""

        # ✅ await 异步调用大模型
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )

        final_answer = response.choices[0].message.content if response.choices else "无法获取回答"
        print(f"最终回答:\n{'-' * 30}\n{final_answer}")

    except Exception as e:
        print(f"发生错误: {e}")


if __name__ == "__main__":
    asyncio.run(main())

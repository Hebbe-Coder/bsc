import sys, asyncio
sys.path.insert(0, r"C:\Users\34216\Documents\New project 3\bsc-backend")
from app.services.llm_adapter import get_llm_adapter, reset_llm_adapter
reset_llm_adapter()
llm = get_llm_adapter()

async def test():
    print("Testing DeepSeek chat...")
    response = await llm.generate(
        prompt="用一句话回答：什么是企业商业分析中最重要的三个维度？",
        system_prompt="你是一个商业分析专家。用中文简洁回答。",
        max_tokens=200,
    )
    print(f"Response: {response[:300]}")
    print()
    print("LLM test PASSED!")

asyncio.run(test())

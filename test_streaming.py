"""
测试脚本 - 验证LangChain重构、异步流式输出和缓存策略
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_llm_service_streaming():
    """测试LLMService同步流式调用"""
    print("\n" + "="*60)
    print("测试1: LLMService同步流式调用")
    print("="*60)
    
    from app.core.llm_service import get_llm_service
    
    service = get_llm_service()
    
    try:
        system_prompt = "你是一个专业的产品经理助手"
        user_prompt = "请简要介绍什么是PRD文档"
        
        print(f"系统提示词: {system_prompt}")
        print(f"用户输入: {user_prompt}")
        print(f"流式输出:")
        
        output = ""
        for token in service.stream_chat(system_prompt, user_prompt):
            output += token
            print(token, end="", flush=True)
        
        print(f"\n输出长度: {len(output)}")
        print("✓ 同步流式调用成功")
        
    except Exception as e:
        print(f"✗ 同步流式调用失败: {e}")


async def test_llm_service_async_streaming():
    """测试LLMService异步流式调用"""
    print("\n" + "="*60)
    print("测试2: LLMService异步流式调用")
    print("="*60)
    
    from app.core.llm_service import get_llm_service
    
    service = get_llm_service()
    
    try:
        system_prompt = "你是一个专业的产品经理助手"
        user_prompt = "请简要介绍什么是用户故事"
        
        print(f"系统提示词: {system_prompt}")
        print(f"用户输入: {user_prompt}")
        print(f"异步流式输出:")
        
        output = ""
        async for token in service.async_stream_chat(system_prompt, user_prompt):
            output += token
            print(token, end="", flush=True)
        
        print(f"\n输出长度: {len(output)}")
        print("✓ 异步流式调用成功")
        
    except Exception as e:
        print(f"✗ 异步流式调用失败: {e}")


async def test_async_llm_service_streaming():
    """测试AsyncLLMService流式调用"""
    print("\n" + "="*60)
    print("测试3: AsyncLLMService流式调用")
    print("="*60)
    
    from app.core.async_llm_service import get_async_llm_service
    
    service = get_async_llm_service()
    
    try:
        system_prompt = "你是一个专业的产品经理助手"
        user_prompt = "请简要介绍什么是产品路线图"
        
        print(f"系统提示词: {system_prompt}")
        print(f"用户输入: {user_prompt}")
        print(f"AsyncLLMService异步流式输出:")
        
        output = ""
        async for token in service.async_stream_chat(system_prompt, user_prompt):
            output += token
            print(token, end="", flush=True)
        
        print(f"\n输出长度: {len(output)}")
        print("✓ AsyncLLMService流式调用成功")
        
    except Exception as e:
        print(f"✗ AsyncLLMService流式调用失败: {e}")


async def test_async_llm_service_buffer():
    """测试AsyncLLMService带缓冲的流式调用"""
    print("\n" + "="*60)
    print("测试4: AsyncLLMService带缓冲的流式调用")
    print("="*60)
    
    from app.core.async_llm_service import get_async_llm_service
    
    service = get_async_llm_service()
    
    try:
        system_prompt = "你是一个专业的产品经理助手"
        user_prompt = "请简要介绍什么是产品需求文档"
        
        print(f"系统提示词: {system_prompt}")
        print(f"用户输入: {user_prompt}")
        print(f"带缓冲的异步流式输出 (buffer_size=50):")
        
        output = ""
        buffer_count = 0
        async for buffer in service.async_stream_chat_with_buffer(
            system_prompt, user_prompt, buffer_size=50
        ):
            output += buffer
            buffer_count += 1
            print(f"[缓冲区{buffer_count}] {buffer}", end="", flush=True)
        
        print(f"\n输出长度: {len(output)}")
        print(f"缓冲区数量: {buffer_count}")
        print("✓ 带缓冲的流式调用成功")
        
    except Exception as e:
        print(f"✗ 带缓冲的流式调用失败: {e}")


async def test_langchain_service():
    """测试LangChainService"""
    print("\n" + "="*60)
    print("测试5: LangChainService异步流式调用")
    print("="*60)
    
    from app.core.langchain_service import get_langchain_service
    
    service = get_langchain_service()
    
    try:
        input_text = "零售电商系统"
        industry = "retail"
        
        print(f"输入文本: {input_text}")
        print(f"行业: {industry}")
        print(f"LangChain异步流式PRD输出:")
        
        output = ""
        async for token in service.astream_generate_prd(input_text, industry, {}):
            output += token
            print(token, end="", flush=True)
        
        print(f"\n输出长度: {len(output)}")
        print("✓ LangChainService异步流式调用成功")
        
    except Exception as e:
        print(f"✗ LangChainService异步流式调用失败: {e}")


async def test_langchain_cache():
    """测试LangChain缓存策略"""
    print("\n" + "="*60)
    print("测试6: LangChain缓存策略")
    print("="*60)
    
    from app.core.langchain_cache import LangChainCache, cache_backed_chain
    from langchain_core.runnables import RunnableLambda
    
    try:
        cache = LangChainCache(ttl=3600, key_prefix="test")
        
        def mock_chain(inputs):
            print(f"  执行实际计算: {inputs}")
            return {"result": f"Result for {inputs['query']}"}
        
        cached_chain = cache_backed_chain(RunnableLambda(mock_chain), cache)
        
        print("第一次调用（应该缓存未命中）:")
        result1 = cached_chain.invoke({"query": "test query"})
        print(f"  结果: {result1}")
        
        print("第二次调用（应该缓存命中）:")
        result2 = cached_chain.invoke({"query": "test query"})
        print(f"  结果: {result2}")
        
        stats = cache.get_stats()
        print(f"\n缓存统计: 命中={stats['hits']}, 未命中={stats['misses']}, 命中率={stats['hit_rate']:.2%}")
        
        if stats["hits"] == 1 and stats["misses"] == 1:
            print("✓ 缓存策略工作正常")
        else:
            print(f"✗ 缓存统计异常: {stats}")
            
    except Exception as e:
        print(f"✗ 缓存策略测试失败: {e}")


async def test_llm_service_async_chat():
    """测试LLMService异步调用"""
    print("\n" + "="*60)
    print("测试7: LLMService异步调用")
    print("="*60)
    
    from app.core.llm_service import get_llm_service
    
    service = get_llm_service()
    
    try:
        system_prompt = "你是一个专业的产品经理助手"
        user_prompt = "请简要介绍什么是MVP"
        
        print(f"系统提示词: {system_prompt}")
        print(f"用户输入: {user_prompt}")
        
        result = await service.async_chat(system_prompt, user_prompt)
        
        print(f"结果类型: {type(result)}")
        print(f"是否包含_meta: { '_meta' in result}")
        if "_meta" in result:
            print(f"_meta: {result['_meta']}")
        print(f"结果长度: {len(str(result))}")
        print("✓ LLMService异步调用成功")
        
    except Exception as e:
        print(f"✗ LLMService异步调用失败: {e}")


async def test_api_import():
    """测试API路由导入"""
    print("\n" + "="*60)
    print("测试8: 验证Stream API路由导入")
    print("="*60)
    
    try:
        from app.api.stream_api import router, StreamChatRequest, StreamPRDRequest, StreamQuestionRequest
        
        print(f"路由前缀: {router.prefix}")
        print(f"路由标签: {router.tags}")
        
        routes = [r.path for r in router.routes]
        print(f"路由列表: {routes}")
        
        expected_routes = [
            "/stream/compile",
            "/stream/{stream_id}",
            "/stream/",
            "/stream/{stream_id}",
            "/stream/chat",
            "/stream/prd",
            "/stream/question",
        ]
        
        for route in ["/stream/chat", "/stream/prd", "/stream/question"]:
            if route in routes:
                print(f"✓ {route} 路由存在")
            else:
                print(f"✗ {route} 路由缺失")
        
        print("✓ Stream API路由导入成功")
        
    except Exception as e:
        print(f"✗ Stream API路由导入失败: {e}")


async def main():
    """主测试函数"""
    print("="*60)
    print("LangChain重构与异步流式输出测试套件")
    print("="*60)
    print("注意: 使用mock模式测试，不调用真实LLM API")
    
    await test_llm_service_streaming()
    await test_llm_service_async_streaming()
    await test_async_llm_service_streaming()
    await test_async_llm_service_buffer()
    await test_langchain_service()
    await test_langchain_cache()
    await test_llm_service_async_chat()
    await test_api_import()
    
    print("\n" + "="*60)
    print("所有测试完成!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
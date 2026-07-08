#!/usr/bin/env python3
"""
LangChain Agent测试脚本

测试Agent服务的核心功能：
1. Agent会话创建
2. Agent对话（工具调用）
3. Agent响应类型检测
4. 与DialogEngine集成
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

def test_agent_service():
    """测试LangChainAgentService"""
    print("=== 测试1: LangChainAgentService ===")
    
    from app.core.langchain_agent import LangChainAgentService
    
    agent = LangChainAgentService(provider="mock", use_mock=True)
    
    session = agent.create_session("test_user", "智能客服系统", "medium", "retail")
    print(f"会话创建成功: {session['session_id']}")
    
    response = agent.chat(session["session_id"], "我想做一个智能客服系统")
    print(f"Agent响应成功")
    print(f"响应类型: {response.get('type')}")
    print(f"响应内容预览: {response.get('response', '')[:100]}...")
    
    return True

def test_agent_tools():
    """测试Agent工具调用"""
    print("\n=== 测试2: Agent工具调用 ===")
    
    from app.core.langchain_agent import PRDGeneratorTool, QuestionGeneratorTool
    from app.core.langchain_service import LangChainService
    
    langchain_service = LangChainService(provider="mock", use_mock=True)
    
    prd_tool = PRDGeneratorTool(langchain_service=langchain_service)
    prd_result = prd_tool._run("智能工单系统", "通用", '{"business_objectives": "提升效率"}')
    print(f"PRD工具调用成功，长度: {len(prd_result)}")
    
    question_tool = QuestionGeneratorTool(langchain_service=langchain_service)
    question_result = question_tool._run("电商系统", "{}", "business_objectives", 1, 5)
    print(f"问题工具调用成功: {question_result[:100]}...")
    
    return True

def test_dialog_engine_agent():
    """测试DialogEngine的Agent模式"""
    print("\n=== 测试3: DialogEngine Agent模式 ===")
    
    from app.core.dialog_engine import DialogEngine
    
    engine = DialogEngine(use_agent=True)
    
    session = engine.create_session("test_user", "智能工单系统", "light", "通用")
    print(f"会话创建成功: {session['session_id']}")
    
    response = engine.agent_chat(session["session_id"], "提升工单处理效率")
    print(f"Agent对话成功")
    print(f"响应类型: {response.get('type')}")
    
    return True

def test_agent_api():
    """测试Agent API"""
    print("\n=== 测试4: Agent API ===")
    
    import asyncio
    from app.api.dialog_api import create_agent_session, agent_chat
    from app.api.dialog_api import CreateSessionRequest, AnswerRequest
    
    async def run_api_test():
        req = CreateSessionRequest(
            user_id="test_user",
            input_text="智能物流系统",
            industry="retail",
            depth="light"
        )
        
        result = await create_agent_session(req)
        print(f"API调用成功")
        print(f"会话ID: {result.data['session_id']}")
        
        session_id = result.data['session_id']
        chat_req = AnswerRequest(answer="优化配送效率")
        
        chat_result = await agent_chat(session_id, chat_req)
        print(f"Agent聊天成功")
        print(f"响应类型: {chat_result.data.get('type')}")
        
        return True
    
    return asyncio.run(run_api_test())

if __name__ == "__main__":
    print("=" * 60)
    print("LangChain Agent集成测试")
    print("=" * 60)
    
    results = []
    try:
        results.append(test_agent_service())
    except Exception as e:
        print(f"测试1失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(False)
    
    try:
        results.append(test_agent_tools())
    except Exception as e:
        print(f"测试2失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(False)
    
    try:
        results.append(test_dialog_engine_agent())
    except Exception as e:
        print(f"测试3失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(False)
    
    try:
        results.append(test_agent_api())
    except Exception as e:
        print(f"测试4失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(False)
    
    print("\n" + "=" * 60)
    if all(results):
        print("✓ 所有测试通过!")
    else:
        print("✗ 部分测试失败")
    print("=" * 60)

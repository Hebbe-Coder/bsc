#!/usr/bin/env python3
"""
最小化LangChain集成测试脚本

不依赖完整的app导入链，只测试LangChain核心功能：
1. MockLLM作为Runnable在LCEL链中工作
2. PRD生成使用StrOutputParser
3. 对话问题生成使用PydanticOutputParser
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LIB_PATH = os.path.join(PROJECT_ROOT, "lib")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, LIB_PATH)

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import SystemMessage, HumanMessage
import json
import re


class DialogQuestionOutput(BaseModel):
    question: str = Field(..., description="生成的问题")
    question_type: str = Field(..., description="问题类型")
    category: str = Field("business", description="问题分类")
    requires_follow_up: bool = Field(False, description="是否需要追问")


class MockLLM:
    """Mock LLM实现，返回字符串"""
    
    def invoke(self, input):
        messages = []
        
        if isinstance(input, dict):
            messages = input.get("messages", [])
        elif hasattr(input, "messages"):
            messages = input.messages
        else:
            return '{"question": "这是一个mock问题"}'
        
        system_content = ""
        human_content = ""
        
        for msg in messages:
            if hasattr(msg, "content"):
                content = msg.content
                role = getattr(msg, "role", "user")
                if role == "system":
                    system_content = content
                else:
                    human_content = content
            elif isinstance(msg, dict):
                if msg.get("role") == "system":
                    system_content = msg.get("content", "")
                else:
                    human_content = msg.get("content", "")
        
        if "PRD" in system_content or "产品需求文档" in system_content or "产品经理" in system_content:
            return self._mock_prd_response(human_content)
        
        if "澄清问题" in system_content or "产品需求分析师" in system_content or "苏格拉底式提问" in system_content:
            return self._mock_question_response(human_content)
        
        return json.dumps({
            "question": "这个产品的核心业务目标是什么？",
            "question_type": "business_objectives",
            "category": "business",
            "requires_follow_up": False,
        }, ensure_ascii=False)
    
    def _mock_prd_response(self, human_content):
        input_text = "测试产品"
        industry = "通用"
        
        name_match = re.search(r"产品名称：(.+?)(?:\n|$)", human_content)
        if name_match:
            input_text = name_match.group(1).strip()
        
        industry_match = re.search(r"行业：(.+?)(?:\n|$)", human_content)
        if industry_match:
            industry = industry_match.group(1).strip()
        
        return f"""# {input_text}产品PRD

## 一、产品概述
本产品是一款面向{industry}领域的业务系统。

## 二、业务目标
提升用户转化率至5%，降低运营成本30%。

## 三、核心功能模块
### 商品管理
- 商品发布和管理

### 订单系统
- 订单创建和履约

## 四、用户角色与权限
- 管理员、普通用户

## 五、业务流程图
```mermaid
flowchart TD
    A[开始] --> B[结束]
```

## 六、非功能需求
- 响应时间<1秒

## 七、成功标准
- 转化率>5%

## 八、项目里程碑
- Phase 1：基础功能上线"""
    
    def _mock_question_response(self, human_content):
        question_type = "business_objectives"
        
        type_match = re.search(r"当前问题类型：(.+?)(?:\n|$)", human_content)
        if type_match:
            question_type = type_match.group(1).strip()
        
        question_map = {
            "business_objectives": "这个产品的核心业务目标是什么？",
            "core_features": "需要哪些核心功能模块？",
            "user_roles": "主要服务哪些用户角色？",
            "业务目标": "这个产品的核心业务目标是什么？",
            "核心功能": "需要哪些核心功能模块？",
            "用户角色": "主要服务哪些用户角色？",
        }
        
        question = question_map.get(question_type, question_map["business_objectives"])
        
        return json.dumps({
            "question": question,
            "question_type": question_type,
            "category": "business",
            "requires_follow_up": False,
        }, ensure_ascii=False)


def test_prd_chain():
    """测试PRD生成链"""
    print("=== 测试1: PRD生成链 ===")
    
    mock_llm = MockLLM()
    llm_runnable = RunnableLambda(mock_llm.invoke)
    str_parser = StrOutputParser()
    
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="你是一个资深的产品经理，擅长撰写PRD。"),
        HumanMessage(content="产品名称：智能电商系统\n行业：零售"),
    ])
    
    chain = prompt | llm_runnable | str_parser
    
    try:
        result = chain.invoke({})
        print(f"✓ 链执行成功")
        print(f"PRD长度: {len(result)}")
        print(f"包含标题: {'# ' in result}")
        print(f"包含章节: {'##' in result}")
        print(f"包含流程图: {'mermaid' in result}")
        return True
    except Exception as e:
        print(f"✗ 链执行失败: {e}")
        return False


def test_question_chain():
    """测试问题生成链"""
    print("\n=== 测试2: 问题生成链 ===")
    
    mock_llm = MockLLM()
    llm_runnable = RunnableLambda(mock_llm.invoke)
    question_parser = PydanticOutputParser(pydantic_object=DialogQuestionOutput)
    
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="你是一个产品需求分析师，擅长苏格拉底式提问。\n{format_instructions}"),
        HumanMessage(content="用户输入：电商系统\n当前问题类型：业务目标"),
    ])
    
    chain = prompt | llm_runnable | question_parser
    
    try:
        result = chain.invoke({
            "format_instructions": question_parser.get_format_instructions()
        })
        print(f"✓ 链执行成功")
        print(f"问题: {result.question}")
        print(f"问题类型: {result.question_type}")
        print(f"分类: {result.category}")
        return True
    except Exception as e:
        print(f"✗ 链执行失败: {e}")
        return False


def test_collected_data_integration():
    """测试收集数据集成"""
    print("\n=== 测试3: 收集数据集成 ===")
    
    mock_llm = MockLLM()
    llm_runnable = RunnableLambda(mock_llm.invoke)
    str_parser = StrOutputParser()
    
    collected_data = {
        "business_objectives": "提升用户转化率至5%",
        "core_features": "商品管理、订单系统",
        "user_roles": "消费者、商家、运营",
    }
    
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="你是一个资深的产品经理。"),
        HumanMessage(content="产品名称：智能电商系统\n行业：零售\n\n收集到的需求信息：\n{collected_data}"),
    ])
    
    chain = prompt | llm_runnable | str_parser
    
    try:
        result = chain.invoke({
            "collected_data": json.dumps(collected_data, ensure_ascii=False)
        })
        print(f"✓ 链执行成功")
        print(f"PRD长度: {len(result)}")
        print(f"包含业务目标: {'提升用户转化率' in result}")
        print(f"包含核心功能: {'商品管理' in result}")
        return True
    except Exception as e:
        print(f"✗ 链执行失败: {e}")
        return False


def test_langchain_service():
    """测试实际的LangChainService类"""
    print("\n=== 测试4: LangChainService类 ===")
    
    try:
        from app.core.langchain_service import LangChainService
        
        service = LangChainService(provider="mock", use_mock=True)
        
        prd_text = service.generate_prd(
            input_text="智能电商系统",
            industry="零售",
            collected_data={
                "business_objectives": "提升用户转化率至5%",
                "core_features": "商品管理、订单系统",
            }
        )
        
        print(f"✓ PRD生成成功")
        print(f"PRD长度: {len(prd_text)}")
        print(f"包含标题: {'# ' in prd_text}")
        print(f"包含章节: {'##' in prd_text}")
        
        question_result = service.generate_dialog_question(
            input_text="电商系统",
            collected_data={},
            question_type="业务目标",
            question_number=1,
            total_questions=3,
        )
        
        print(f"✓ 问题生成成功")
        print(f"问题: {question_result.question}")
        print(f"问题类型: {question_result.question_type}")
        
        return True
    except Exception as e:
        print(f"✗ LangChainService测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("LangChain最小化集成测试")
    print("=" * 60)
    
    results = []
    results.append(test_prd_chain())
    results.append(test_question_chain())
    results.append(test_collected_data_integration())
    results.append(test_langchain_service())
    
    print("\n" + "=" * 60)
    if all(results):
        print("✓ 所有测试通过!")
        print("LangChain集成正常工作")
    else:
        print("✗ 部分测试失败，请检查错误信息")
    print("=" * 60)
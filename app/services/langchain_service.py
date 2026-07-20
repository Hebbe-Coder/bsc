"""
LangChain Service - LangChain集成服务

提供基于LangChain Expression Language的高级LLM编排能力：
1. PydanticOutputParser - 结构化输出解析（用于对话问题）
2. StrOutputParser - 字符串输出解析（用于PRD生成，LLM擅长直接生成markdown）
3. ChatPromptTemplate - 安全的prompt模板，替代f-string拼接
4. LCEL Chain - 可复用的链式调用，简化多轮对话逻辑
5. RunnableCache - 缓存策略，减少重复调用
6. Async/Astream - 异步调用和流式输出支持
7. Mock模式支持 - 保留开发测试能力

设计原则：
- 增量替换：不破坏现有LLMService，通过feature flag切换
- 类型安全：使用Pydantic模型确保输出结构正确
- 可扩展性：LCEL Chain易于扩展和组合
- 兼容性：支持所有现有Provider（deepseek/doubao/yuanbao/mock/ollama/vllm/localai）
- 实用优先：PRD生成直接输出markdown，问题生成使用结构化输出
"""
from __future__ import annotations
import json
import logging
import re
import time
from typing import Dict, Any, Optional, List, AsyncIterator, Iterator
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.runnables import (
    RunnableLambda,
)
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import AsyncCallbackHandler
from app.core.llm_policy import ensure_fallback_allowed, ensure_mock_allowed

logger = logging.getLogger(__name__)


class DialogQuestionOutput(BaseModel):
    """对话问题输出结构"""
    question: str = Field(..., description="生成的问题")
    question_type: str = Field(..., description="问题类型")
    category: str = Field("business", description="问题分类")
    requires_follow_up: bool = Field(False, description="是否需要追问")


class LLMResponse(BaseModel):
    """统一LLM响应结构"""
    content: str = Field(..., description="响应内容")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class LangChainCache:
    """基于项目缓存服务的LCEL缓存实现"""
    
    def __init__(self, ttl: int = 3600):
        self._ttl = ttl
    
    def lookup(self, key: str) -> Optional[Any]:
        """从缓存查找结果"""
        try:
            from app.services.cache_service import get_cache_service
            cache = get_cache_service()
            if cache and cache.exists(key):
                return cache.get(key)
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")
        return None
    
    def update(self, key: str, value: Any) -> None:
        """更新缓存"""
        try:
            from app.services.cache_service import get_cache_service
            cache = get_cache_service()
            if cache:
                cache.set(key, value, self._ttl)
        except Exception as e:
            logger.warning(f"Cache update failed: {e}")


class AsyncStreamingCallbackHandler(AsyncCallbackHandler):
    """异步流式回调处理器"""
    
    def __init__(self, callback):
        self.callback = callback
    
    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        """新token到达时触发回调"""
        await self.callback(token)


class StreamingCallbackHandler:
    """同步流式回调处理器"""
    
    def __init__(self, callback):
        self.callback = callback
    
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """新token到达时触发回调"""
        self.callback(token)


class LangChainService:
    """LangChain服务"""
    
    def __init__(self, provider: str = None, use_mock: bool = None):
        self.provider = provider or self._get_settings().LLM_PROVIDER
        self.use_mock = use_mock if use_mock is not None else (self.provider == "mock")
        if self.use_mock:
            ensure_mock_allowed("LangChain")
        self._llm = None
        self._async_llm = None
        self._question_parser = PydanticOutputParser(pydantic_object=DialogQuestionOutput)
        self._str_parser = StrOutputParser()
        self._cache = LangChainCache()
        self._prd_chain = None
        self._question_chain = None
    
    def _get_settings(self):
        """懒加载配置"""
        from app.core.config import settings
        return settings
    
    @property
    def llm(self):
        """懒加载同步LLM实例"""
        if self._llm is None:
            if self.use_mock:
                ensure_mock_allowed("LangChain")
                mock_llm = MockLLM()
                self._llm = RunnableLambda(mock_llm.invoke)
            else:
                self._llm = self._create_sync_llm()
        return self._llm
    
    @property
    def async_llm(self):
        """懒加载异步LLM实例"""
        if self._async_llm is None:
            if self.use_mock:
                ensure_mock_allowed("LangChain")
                mock_llm = MockLLM()
                self._async_llm = RunnableLambda(mock_llm.invoke)
            else:
                self._async_llm = self._create_async_llm()
        return self._async_llm
    
    def _get_provider_config(self, provider: str) -> Optional[Dict[str, str]]:
        """获取Provider配置"""
        settings = self._get_settings()
        provider_config = {
            "deepseek": {
                "api_key": settings.DEEPSEEK_API_KEY,
                "base_url": settings.DEEPSEEK_BASE_URL,
                "model": settings.DEEPSEEK_MODEL,
            },
            "doubao": {
                "api_key": settings.DOUBAO_API_KEY,
                "base_url": settings.DOUBAO_BASE_URL,
                "model": settings.DOUBAO_MODEL,
            },
            "yuanbao": {
                "api_key": settings.YUANBAO_API_KEY,
                "base_url": settings.YUANBAO_BASE_URL,
                "model": settings.YUANBAO_MODEL,
            },
            "qwen": {
                "api_key": settings.QWEN_API_KEY,
                "base_url": settings.QWEN_BASE_URL,
                "model": settings.QWEN_MODEL,
            },
            "ollama": {
                "api_key": "ollama",
                "base_url": settings.OLLAMA_BASE_URL,
                "model": settings.OLLAMA_MODEL,
            },
            "vllm": {
                "api_key": "vllm",
                "base_url": settings.VLLM_BASE_URL,
                "model": settings.VLLM_MODEL or "default",
            },
            "localai": {
                "api_key": "localai",
                "base_url": settings.LOCALAI_BASE_URL,
                "model": settings.LOCALAI_MODEL,
            },
        }
        return provider_config.get(provider)
    
    def _create_sync_llm(self) -> ChatOpenAI:
        """创建同步LLM实例"""
        config = self._get_provider_config(self.provider)
        if not config or not config["api_key"]:
            logger.warning(f"No valid API key for {self.provider}, falling back to mock")
            ensure_fallback_allowed("LangChain")
            self.use_mock = True
            mock_llm = MockLLM()
            return RunnableLambda(mock_llm.invoke)
        
        settings = self._get_settings()
        return ChatOpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            timeout=settings.LLM_TIMEOUT,
        )
    
    def _create_async_llm(self) -> ChatOpenAI:
        """创建异步LLM实例（ChatOpenAI同时支持同步和异步调用）"""
        config = self._get_provider_config(self.provider)
        if not config or not config["api_key"]:
            logger.warning(f"No valid API key for {self.provider}, falling back to mock")
            ensure_fallback_allowed("LangChain")
            self.use_mock = True
            mock_llm = MockLLM()
            return RunnableLambda(mock_llm.invoke)
        
        settings = self._get_settings()
        return ChatOpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            timeout=settings.LLM_TIMEOUT,
        )
    
    @property
    def prd_chain(self):
        """PRD生成链（带缓存）"""
        if self._prd_chain is None:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content="""你是一个资深的产品经理，擅长撰写专业、完整、结构化的产品需求文档（PRD）。

请根据收集到的需求信息，生成一份高质量的PRD文档。

要求：
1. 结构完整：包含业务目标、核心功能、用户角色、业务流程、非功能需求等章节
2. 内容专业：每个章节要有详细的描述，不仅仅是简单罗列
3. 格式规范：使用Markdown格式，标题层级清晰
4. 示例丰富：为每个功能模块提供具体的功能点示例
5. 语言专业但易懂：使用产品经理常用的专业术语，但保持可读性
6. 补充完整：对于用户未明确的内容，基于行业最佳实践进行合理补充

PRD结构要求：
# 产品名称PRD
## 一、产品概述
## 二、业务目标（可量化）
## 三、核心功能模块（每个模块详细描述）
## 四、用户角色与权限
## 五、业务流程图
## 六、非功能需求
## 七、成功标准
## 八、项目里程碑

请确保输出是一份完整、专业的PRD文档，而不是简单的信息罗列。"""),
                HumanMessage(content="""产品名称：{input_text}
行业：{industry}

收集到的需求信息：
{collected_data}

请基于以上信息，生成一份专业、完整的PRD文档："""),
            ])
            self._prd_chain = prompt | self.llm | self._str_parser
        return self._prd_chain
    
    @property
    def async_prd_chain(self):
        """异步PRD生成链"""
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""你是一个资深的产品经理，擅长撰写专业、完整、结构化的产品需求文档（PRD）。

请根据收集到的需求信息，生成一份高质量的PRD文档。

要求：
1. 结构完整：包含业务目标、核心功能、用户角色、业务流程、非功能需求等章节
2. 内容专业：每个章节要有详细的描述，不仅仅是简单罗列
3. 格式规范：使用Markdown格式，标题层级清晰
4. 示例丰富：为每个功能模块提供具体的功能点示例
5. 语言专业但易懂：使用产品经理常用的专业术语，但保持可读性
6. 补充完整：对于用户未明确的内容，基于行业最佳实践进行合理补充

PRD结构要求：
# 产品名称PRD
## 一、产品概述
## 二、业务目标（可量化）
## 三、核心功能模块（每个模块详细描述）
## 四、用户角色与权限
## 五、业务流程图
## 六、非功能需求
## 七、成功标准
## 八、项目里程碑

请确保输出是一份完整、专业的PRD文档，而不是简单的信息罗列。"""),
            HumanMessage(content="""产品名称：{input_text}
行业：{industry}

收集到的需求信息：
{collected_data}

请基于以上信息，生成一份专业、完整的PRD文档："""),
        ])
        return prompt | self.async_llm | self._str_parser
    
    @property
    def question_chain(self):
        """问题生成链（带缓存）"""
        if self._question_chain is None:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content="""你是一个专业的产品需求分析师，擅长通过苏格拉底式提问帮助产品经理理清需求。

请根据用户的输入和已收集的信息，生成一个上下文相关的澄清问题。

要求：
1. 问题必须针对当前对话主题，引用用户提到的具体内容
2. 问题要引导用户提供更具体、更深入的信息
3. 使用自然、友好的语言，避免机械感
4. 只输出问题本身，不要包含其他内容

{format_instructions}"""),
                HumanMessage(content="""用户输入：{input_text}
已收集信息：{collected_data}
当前问题类型：{question_type}
当前问题序号：{question_number}/{total_questions}

请生成下一个澄清问题："""),
            ])
            self._question_chain = prompt | self.llm | self._question_parser
        return self._question_chain
    
    @property
    def async_question_chain(self):
        """异步问题生成链"""
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""你是一个专业的产品需求分析师，擅长通过苏格拉底式提问帮助产品经理理清需求。

请根据用户的输入和已收集的信息，生成一个上下文相关的澄清问题。

要求：
1. 问题必须针对当前对话主题，引用用户提到的具体内容
2. 问题要引导用户提供更具体、更深入的信息
3. 使用自然、友好的语言，避免机械感
4. 只输出问题本身，不要包含其他内容

{format_instructions}"""),
            HumanMessage(content="""用户输入：{input_text}
已收集信息：{collected_data}
当前问题类型：{question_type}
当前问题序号：{question_number}/{total_questions}

请生成下一个澄清问题："""),
        ])
        return prompt | self.async_llm | self._question_parser
    
    def generate_prd(self, input_text: str, industry: str, 
                     collected_data: Dict[str, str], use_cache: bool = True) -> str:
        """
        同步生成PRD文档
        
        Args:
            input_text: 用户输入
            industry: 行业类型
            collected_data: 收集的数据
            use_cache: 是否使用缓存
            
        Returns:
            PRD markdown文本
        """
        chain = self._wrap_with_cache(self.prd_chain) if use_cache else self.prd_chain
        
        try:
            prd_text = chain.invoke({
                "input_text": input_text,
                "industry": industry,
                "collected_data": json.dumps(collected_data, ensure_ascii=False, indent=2),
            })
            
            if prd_text and len(prd_text) > 100:
                logger.info("Successfully generated PRD using LangChain")
                return prd_text
            
            logger.warning("LangChain PRD generation returned empty or too short, falling back")
            return self._fallback_prd_markdown(input_text, industry, collected_data)
                
        except Exception as e:
            logger.error(f"LangChain PRD generation failed: {e}, falling back")
            return self._fallback_prd_markdown(input_text, industry, collected_data)
    
    async def async_generate_prd(self, input_text: str, industry: str, 
                                 collected_data: Dict[str, str], use_cache: bool = True) -> str:
        """
        异步生成PRD文档
        
        Args:
            input_text: 用户输入
            industry: 行业类型
            collected_data: 收集的数据
            use_cache: 是否使用缓存
            
        Returns:
            PRD markdown文本
        """
        chain = self._wrap_with_cache(self.async_prd_chain) if use_cache else self.async_prd_chain
        
        try:
            prd_text = await chain.ainvoke({
                "input_text": input_text,
                "industry": industry,
                "collected_data": json.dumps(collected_data, ensure_ascii=False, indent=2),
            })
            
            if prd_text and len(prd_text) > 100:
                logger.info("Successfully generated PRD using LangChain async")
                return prd_text
            
            logger.warning("LangChain async PRD generation returned empty or too short, falling back")
            return self._fallback_prd_markdown(input_text, industry, collected_data)
                
        except Exception as e:
            logger.error(f"LangChain async PRD generation failed: {e}, falling back")
            return self._fallback_prd_markdown(input_text, industry, collected_data)
    
    def stream_generate_prd(self, input_text: str, industry: str, 
                            collected_data: Dict[str, str]) -> Iterator[str]:
        """
        同步流式生成PRD文档
        
        Args:
            input_text: 用户输入
            industry: 行业类型
            collected_data: 收集的数据
            
        Returns:
            流式token迭代器
        """
        try:
            for token in self.prd_chain.stream({
                "input_text": input_text,
                "industry": industry,
                "collected_data": json.dumps(collected_data, ensure_ascii=False, indent=2),
            }):
                yield token
        except Exception as e:
            logger.error(f"LangChain stream PRD generation failed: {e}")
            fallback = self._fallback_prd_markdown(input_text, industry, collected_data)
            for token in fallback.split("\n"):
                yield token + "\n"
    
    async def astream_generate_prd(self, input_text: str, industry: str, 
                                   collected_data: Dict[str, str]) -> AsyncIterator[str]:
        """
        异步流式生成PRD文档
        
        Args:
            input_text: 用户输入
            industry: 行业类型
            collected_data: 收集的数据
            
        Returns:
            异步流式token迭代器
        """
        try:
            async for token in self.async_prd_chain.astream({
                "input_text": input_text,
                "industry": industry,
                "collected_data": json.dumps(collected_data, ensure_ascii=False, indent=2),
            }):
                yield token
        except Exception as e:
            logger.error(f"LangChain async stream PRD generation failed: {e}")
            fallback = self._fallback_prd_markdown(input_text, industry, collected_data)
            for token in fallback.split("\n"):
                yield token + "\n"
    
    def generate_dialog_question(self, input_text: str, collected_data: Dict[str, str],
                                  question_type: str, question_number: int, 
                                  total_questions: int, use_cache: bool = True) -> DialogQuestionOutput:
        """
        同步生成对话问题
        
        Args:
            input_text: 用户输入
            collected_data: 已收集的数据
            question_type: 问题类型
            question_number: 当前问题序号
            total_questions: 总问题数
            use_cache: 是否使用缓存
            
        Returns:
            DialogQuestionOutput: 结构化问题输出
        """
        chain = self._wrap_with_cache(self.question_chain) if use_cache else self.question_chain
        
        try:
            result = chain.invoke({
                "input_text": input_text,
                "collected_data": json.dumps(collected_data, ensure_ascii=False),
                "question_type": question_type,
                "question_number": question_number,
                "total_questions": total_questions,
                "format_instructions": self._question_parser.get_format_instructions(),
            })
            
            if isinstance(result, DialogQuestionOutput):
                return result
            elif isinstance(result, dict):
                return DialogQuestionOutput(**result)
            else:
                return self._fallback_question(input_text, question_type)
                
        except Exception as e:
            logger.error(f"LangChain question generation failed: {e}, falling back")
            return self._fallback_question(input_text, question_type)
    
    async def async_generate_dialog_question(self, input_text: str, collected_data: Dict[str, str],
                                              question_type: str, question_number: int, 
                                              total_questions: int, use_cache: bool = True) -> DialogQuestionOutput:
        """
        异步生成对话问题
        
        Args:
            input_text: 用户输入
            collected_data: 已收集的数据
            question_type: 问题类型
            question_number: 当前问题序号
            total_questions: 总问题数
            use_cache: 是否使用缓存
            
        Returns:
            DialogQuestionOutput: 结构化问题输出
        """
        chain = self._wrap_with_cache(self.async_question_chain) if use_cache else self.async_question_chain
        
        try:
            result = await chain.ainvoke({
                "input_text": input_text,
                "collected_data": json.dumps(collected_data, ensure_ascii=False),
                "question_type": question_type,
                "question_number": question_number,
                "total_questions": total_questions,
                "format_instructions": self._question_parser.get_format_instructions(),
            })
            
            if isinstance(result, DialogQuestionOutput):
                return result
            elif isinstance(result, dict):
                return DialogQuestionOutput(**result)
            else:
                return self._fallback_question(input_text, question_type)
                
        except Exception as e:
            logger.error(f"LangChain async question generation failed: {e}, falling back")
            return self._fallback_question(input_text, question_type)
    
    def chat(self, system_prompt: str, user_prompt: str, 
             temperature: float = None, max_tokens: int = None,
             use_cache: bool = True, response_format: str = "text") -> str:
        """
        通用同步聊天接口
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户输入
            temperature: 温度
            max_tokens: 最大输出长度
            use_cache: 是否使用缓存
            response_format: 输出格式（text/json）
            
        Returns:
            字符串响应
        """
        settings = self._get_settings()
        temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        mt = max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        
        llm = self.llm
        if isinstance(llm, ChatOpenAI):
            llm = llm.bind(temperature=temp, max_tokens=mt)
            if response_format == "json":
                llm = llm.bind(response_format={"type": "json_object"})
        
        chain = prompt | llm | self._str_parser
        
        if use_cache:
            chain = self._wrap_with_cache(chain)
        
        try:
            result = chain.invoke({})
            return result
        except Exception as e:
            logger.error(f"LangChain chat failed: {e}")
            return f"Error: {str(e)}"
    
    async def async_chat(self, system_prompt: str, user_prompt: str, 
                         temperature: float = None, max_tokens: int = None,
                         use_cache: bool = True, response_format: str = "text") -> str:
        """
        通用异步聊天接口
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户输入
            temperature: 温度
            max_tokens: 最大输出长度
            use_cache: 是否使用缓存
            response_format: 输出格式（text/json）
            
        Returns:
            字符串响应
        """
        settings = self._get_settings()
        temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        mt = max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        
        llm = self.async_llm
        if isinstance(llm, ChatOpenAI):
            llm = llm.bind(temperature=temp, max_tokens=mt)
            if response_format == "json":
                llm = llm.bind(response_format={"type": "json_object"})
        
        chain = prompt | llm | self._str_parser
        
        if use_cache:
            chain = self._wrap_with_cache(chain)
        
        try:
            result = await chain.ainvoke({})
            return result
        except Exception as e:
            logger.error(f"LangChain async chat failed: {e}")
            return f"Error: {str(e)}"
    
    def stream_chat(self, system_prompt: str, user_prompt: str, 
                    temperature: float = None, max_tokens: int = None) -> Iterator[str]:
        """
        通用同步流式聊天接口
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户输入
            temperature: 温度
            max_tokens: 最大输出长度
            
        Returns:
            流式token迭代器
        """
        settings = self._get_settings()
        temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        mt = max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        
        llm = self.llm
        if isinstance(llm, ChatOpenAI):
            llm = llm.bind(temperature=temp, max_tokens=mt)
        
        chain = prompt | llm | self._str_parser
        
        try:
            for token in chain.stream({}):
                yield token
        except Exception as e:
            logger.error(f"LangChain stream chat failed: {e}")
            yield f"Error: {str(e)}"
    
    async def astream_chat(self, system_prompt: str, user_prompt: str, 
                           temperature: float = None, max_tokens: int = None) -> AsyncIterator[str]:
        """
        通用异步流式聊天接口
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户输入
            temperature: 温度
            max_tokens: 最大输出长度
            
        Returns:
            异步流式token迭代器
        """
        settings = self._get_settings()
        temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        mt = max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        
        llm = self.async_llm
        if isinstance(llm, ChatOpenAI):
            llm = llm.bind(temperature=temp, max_tokens=mt)
        
        chain = prompt | llm | self._str_parser
        
        try:
            async for token in chain.astream({}):
                yield token
        except Exception as e:
            logger.error(f"LangChain async stream chat failed: {e}")
            yield f"Error: {str(e)}"
    
    def batch_chat(self, requests: List[Dict[str, Any]], 
                   temperature: float = None, max_tokens: int = None) -> List[str]:
        """
        批量同步聊天接口
        
        Args:
            requests: 请求列表
            temperature: 温度
            max_tokens: 最大输出长度
            
        Returns:
            结果列表
        """
        settings = self._get_settings()
        temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        mt = max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS
        
        prompts = []
        for req in requests:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=req.get("system_prompt", "")),
                HumanMessage(content=req.get("user_prompt", "")),
            ])
            prompts.append(prompt)
        
        llm = self.llm
        if isinstance(llm, ChatOpenAI):
            llm = llm.bind(temperature=temp, max_tokens=mt)
        
        chain = prompts | llm | self._str_parser
        
        try:
            results = chain.batch([{} for _ in requests])
            return results
        except Exception as e:
            logger.error(f"LangChain batch chat failed: {e}")
            return [f"Error: {str(e)}" for _ in requests]
    
    def _wrap_with_cache(self, chain):
        """为链添加缓存"""
        if self.use_mock:
            return chain
        try:
            return chain.with_config(cache=self._cache)
        except Exception as e:
            logger.warning(f"Failed to add cache to chain: {e}")
            return chain
    
    def _fallback_prd_markdown(self, input_text: str, industry: str, 
                               collected_data: Dict[str, str]) -> str:
        """生成fallback PRD markdown"""
        ensure_fallback_allowed("LangChain")
        objectives = collected_data.get("business_objectives", "待确认")
        features = collected_data.get("core_features", """### 核心功能模块1
- 功能点1：详细描述功能的价值和作用
- 功能点2：详细描述功能的价值和作用

### 核心功能模块2
- 功能点1：详细描述功能的价值和作用
- 功能点2：详细描述功能的价值和作用""")
        roles = collected_data.get("user_roles", """### 管理员
- 职责：系统管理、用户管理、配置管理
- 权限：全部权限

### 普通用户
- 职责：使用系统核心功能
- 权限：只读和操作权限

### 运营人员
- 职责：业务运营、数据监控
- 权限：运营相关权限""")
        nfr = collected_data.get("non_functional", """### 性能要求
- 响应时间：核心页面<2秒，API<500ms
- QPS：峰值>1000
- 可用性：99.9%

### 安全要求
- 数据加密：传输加密（HTTPS）、存储加密
- 访问控制：基于角色的权限控制
- 日志审计：完整的操作日志记录

### 合规要求
- 数据合规：符合行业数据保护规范
- 隐私保护：用户隐私数据保护措施""")
        success = collected_data.get("success_criteria", """### 业务指标
- 用户增长：月活用户增长率>20%
- 转化率：注册转化率>10%
- 留存率：7日留存>40%

### 技术指标
- 系统可用性：>99.9%
- 响应时间：<2秒
- 错误率：<0.1%

### 用户指标
- 用户满意度：>4.5分（5分制）
- NPS评分：>50""")
        milestones = collected_data.get("milestones", """### Phase 1：基础功能（第1-4周）
- 完成核心功能开发
- 内部测试通过
- 目标：MVP版本上线

### Phase 2：高级功能（第5-8周）
- 完成高级功能开发
- 性能优化
- 目标：功能完善版本上线

### Phase 3：优化迭代（第9-12周）
- 用户反馈收集和分析
- Bug修复和体验优化
- 目标：稳定运营版本""")
        
        return f"""# {input_text}产品PRD

## 基本信息
- 行业：{industry}
- 生成方式：LangChain合成（fallback）

---

## 一、产品概述

本产品是一款面向{industry}领域的业务系统，旨在提升业务效率，优化用户体验，实现数字化转型目标。

## 二、业务目标

{objectives}

## 三、核心功能模块

{features}

## 四、用户角色与权限

{roles}

## 五、业务流程图

```mermaid
flowchart TD
    A[用户访问] --> B[浏览产品]
    B --> C[选择功能]
    C --> D[完成操作]
    D --> E[获取结果]
```

## 六、非功能需求

{nfr}

## 七、成功标准

{success}

## 八、项目里程碑

{milestones}

---

## 质量评估
### 评分因素
- PRD已生成，建议检查内容完整性"""
    
    def _fallback_question(self, input_text: str, question_type: str) -> DialogQuestionOutput:
        """生成fallback问题"""
        ensure_fallback_allowed("LangChain")
        question_map = {
            "business_objectives": "这个产品的核心业务目标是什么？比如是提升效率、降低成本还是增加收益？",
            "core_features": "为了达成业务目标，你认为系统需要哪些核心功能模块？",
            "user_roles": "系统主要服务哪些用户角色？",
            "special_requirements": "有没有特殊的技术或业务要求？",
            "non_functional": "对系统性能、安全等非功能需求有什么要求？",
            "success_criteria": "如何衡量项目成功？有哪些关键指标？",
            "industry_context": "这个产品在行业中的定位是什么？",
            "competitors": "主要竞争对手有哪些？",
            "risks": "项目可能面临哪些风险？",
            "milestones": "项目的关键里程碑是什么？",
            "业务目标": "这个产品的核心业务目标是什么？比如是提升效率、降低成本还是增加收益？",
            "核心功能": "为了达成业务目标，你认为系统需要哪些核心功能模块？",
            "用户角色": "系统主要服务哪些用户角色？",
            "特殊要求": "有没有特殊的技术或业务要求？",
            "非功能需求": "对系统性能、安全等非功能需求有什么要求？",
            "成功标准": "如何衡量项目成功？有哪些关键指标？",
        }
        
        question = question_map.get(question_type, question_map["business_objectives"])
        
        return DialogQuestionOutput(
            question=question,
            question_type=question_type,
            category="business",
            requires_follow_up=False,
        )


class MockLLM:
    """Mock LLM实现，用于开发测试"""
    
    def invoke(self, input: Any) -> str:
        """模拟LLM调用，返回字符串内容"""
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
            if hasattr(msg, "role"):
                if msg.role == "system":
                    system_content = msg.content
                elif msg.role == "user":
                    human_content = msg.content
            elif isinstance(msg, dict):
                if msg.get("role") == "system":
                    system_content = msg.get("content", "")
                elif msg.get("role") == "user":
                    human_content = msg.get("content", "")
        
        if "PRD" in system_content or "产品需求文档" in system_content:
            return self._mock_prd_response(human_content)
        
        if "澄清问题" in system_content or "产品需求分析师" in system_content:
            return self._mock_question_response(human_content)
        
        return '{"content": "mock response"}'
    
    async def ainvoke(self, input: Any) -> str:
        """异步模拟LLM调用"""
        return self.invoke(input)
    
    def stream(self, input: Any) -> Iterator[str]:
        """模拟流式输出"""
        result = self.invoke(input)
        for chunk in result.split("\n"):
            yield chunk + "\n"
            time.sleep(0.05)
    
    async def astream(self, input: Any) -> AsyncIterator[str]:
        """异步模拟流式输出"""
        result = self.invoke(input)
        for chunk in result.split("\n"):
            yield chunk + "\n"
            time.sleep(0.05)
    
    def _mock_prd_response(self, human_content: str) -> str:
        """模拟PRD响应（直接输出markdown）"""
        input_text = "产品PRD"
        industry = "通用"
        collected_data = {}
        
        name_match = re.search(r"产品名称：(.+?)(?:\n|$)", human_content)
        if name_match:
            input_text = name_match.group(1).strip()
        
        industry_match = re.search(r"行业：(.+?)(?:\n|$)", human_content)
        if industry_match:
            industry = industry_match.group(1).strip()
        
        data_match = re.search(r"收集到的需求信息：(.+)", human_content, re.DOTALL)
        if data_match:
            try:
                collected_data = json.loads(data_match.group(1).strip())
            except:
                pass
        
        objectives = collected_data.get("business_objectives", "待确认\n\n建议按照SMART原则细化：\n- 短期目标（1-3个月）：完成MVP版本上线，验证商业模式\n- 中期目标（3-6个月）：获取目标用户，建立产品口碑\n- 长期目标（6-12个月）：实现盈利，建立行业影响力")
        features = collected_data.get("core_features", """### 商品管理模块
- 商品发布：支持多规格商品、图片上传、库存管理
- 商品搜索：支持关键词搜索、分类筛选、智能推荐
- 商品管理：上下架管理、价格调整、促销活动设置

### 订单系统模块
- 订单创建：支持多种支付方式、地址管理、优惠券使用
- 订单履约：自动化配送流程、物流追踪、退换货管理

### 用户中心模块
- 会员体系：积分和等级制度、成长值计算
- 优惠券：营销活动支持、优惠券发放和使用""")
        roles = collected_data.get("user_roles", """### 消费者
- 职责：浏览商品、下单购买、评价反馈
- 权限：查看商品、提交订单、管理账户

### 商家
- 职责：商品管理、订单处理、数据分析
- 权限：商品上下架、订单处理、数据查看

### 平台运营
- 职责：活动策划、商家管理、平台监控
- 权限：活动配置、商家审核、数据统计""")
        
        return f"""# {input_text}产品PRD

## 基本信息
- 行业：{industry}
- 生成方式：LangChain Mock模式

---

## 一、产品概述

本产品是一款面向{industry}领域的业务系统，旨在通过数字化手段提升用户体验，优化运营效率，实现业务增长目标。

## 二、业务目标

{objectives}

## 三、核心功能模块

{features}

## 四、用户角色与权限

{roles}

## 五、业务流程图

```mermaid
flowchart TD
    A[用户浏览] --> B[搜索/筛选商品]
    B --> C[查看商品详情]
    C --> D[加入购物车]
    D --> E[提交订单]
    E --> F[选择支付方式]
    F --> G[支付成功]
    G --> H[商家发货]
    H --> I[用户收货]
    I --> J[评价反馈]
```

## 六、非功能需求

### 性能要求
- 页面响应时间：<1秒
- 峰值QPS：>10000
- 系统可用性：99.9%

### 安全要求
- 支付安全：符合PCI-DSS标准
- 数据加密：传输和存储加密
- 防攻击：防DDoS、防SQL注入

### 合规要求
- 消费者保护：符合消费者权益保护法
- 数据合规：符合个人信息保护法

## 七、成功标准

### 业务指标
- 转化率：>5%
- 复购率：>30%
- GMV增长率：>30%/月

### 技术指标
- 页面响应时间：<1秒
- 系统可用性：99.9%
- 订单成功率：>99.5%

### 用户指标
- 用户满意度：>4.5分
- NPS评分：>50

## 八、项目里程碑

### Phase 1：基础电商（第1-4周）
- 商品管理、订单系统开发
- 支付接口集成
- 目标：基础购物流程打通

### Phase 2：用户体系（第5-8周）
- 会员体系开发
- 优惠券系统开发
- 目标：用户运营能力完善

### Phase 3：数据分析（第9-12周）
- 数据报表开发
- 智能推荐上线
- 目标：数据驱动运营

---

## 质量评估
### 评分因素
- PRD已生成，建议检查内容完整性"""
    
    def _mock_question_response(self, human_content: str) -> str:
        """模拟问题响应（输出JSON格式）"""
        question_type = "business_objectives"
        
        type_match = re.search(r"当前问题类型：(.+?)(?:\n|$)", human_content)
        if type_match:
            question_type = type_match.group(1).strip()
        
        question_map = {
            "business_objectives": "这个产品的核心业务目标是什么？比如是提升效率、降低成本还是增加收益？",
            "core_features": "为了达成业务目标，你认为系统需要哪些核心功能模块？",
            "user_roles": "系统主要服务哪些用户角色？",
            "special_requirements": "有没有特殊的技术或业务要求？",
            "non_functional": "对系统性能、安全等非功能需求有什么要求？",
            "success_criteria": "如何衡量项目成功？有哪些关键指标？",
            "industry_context": "这个产品在行业中的定位是什么？",
            "competitors": "主要竞争对手有哪些？",
            "risks": "项目可能面临哪些风险？",
            "milestones": "项目的关键里程碑是什么？",
            "业务目标": "这个产品的核心业务目标是什么？比如是提升效率、降低成本还是增加收益？",
            "核心功能": "为了达成业务目标，你认为系统需要哪些核心功能模块？",
            "用户角色": "系统主要服务哪些用户角色？",
            "特殊要求": "有没有特殊的技术或业务要求？",
            "非功能需求": "对系统性能、安全等非功能需求有什么要求？",
            "成功标准": "如何衡量项目成功？有哪些关键指标？",
        }
        
        question = question_map.get(question_type, question_map["business_objectives"])
        
        return json.dumps({
            "question": question,
            "question_type": question_type,
            "category": "business",
            "requires_follow_up": False,
        }, ensure_ascii=False)


__all__ = [
    "LangChainService", 
    "DialogQuestionOutput", 
    "LLMResponse",
    "LangChainCache",
    "AsyncStreamingCallbackHandler",
    "StreamingCallbackHandler",
    "get_langchain_service",
]


import threading

_thread_local = threading.local()


def get_thread_local_langchain_service() -> LangChainService:
    """获取线程本地的LangChain服务实例"""
    if not hasattr(_thread_local, 'langchain_service'):
        _thread_local.langchain_service = LangChainService()
    return _thread_local.langchain_service


_global_langchain_service = None
_global_lock = threading.Lock()


def get_langchain_service() -> LangChainService:
    """获取LangChain服务实例（线程安全的工厂函数）"""
    try:
        return get_thread_local_langchain_service()
    except Exception as e:
        logger.debug(f"Thread-local LangChain service not available: {e}, using global instance")
        global _global_langchain_service
        if _global_langchain_service is None:
            with _global_lock:
                if _global_langchain_service is None:
                    _global_langchain_service = LangChainService()
        return _global_langchain_service

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.services.langchain_service import get_langchain_service


class PresentationGenerationChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        lc_service = get_langchain_service()
        lc_service.provider = provider
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个演示文稿专家，擅长设计和生成PPT大纲。
请根据以下业务内容，生成完整的PPT演示大纲：
1. 封面页
2. 概述页
3. 核心内容页
4. 技术架构页
5. 市场分析页
6. 实施计划页
7. 预期成果页
8. Q&A页

输出格式要求：使用清晰的结构化格式。"""),
            ("human", "{business_content}")
        ])
        
        llm = lc_service.llm
        
        chain = prompt | llm | StrOutputParser()
        return chain

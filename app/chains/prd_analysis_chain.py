from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.services.langchain_service import get_langchain_service


class PrdAnalysisChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        lc_service = get_langchain_service()
        lc_service.provider = provider
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个专业的产品经理，擅长分析产品需求文档(PRD)并提取关键信息。
请分析以下PRD文档，提取：
1. 产品目标
2. 核心功能
3. 目标用户
4. 技术要求
5. 成功指标

输出格式要求：使用清晰的结构化格式，包含以上5个部分，每个部分使用标题和列表。"""),
            ("human", "{prd_content}")
        ])
        
        llm = lc_service.llm
        
        chain = prompt | llm | StrOutputParser()
        return chain

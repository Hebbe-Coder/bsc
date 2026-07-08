from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.services.langchain_service import get_langchain_service


class ObjectiveExtractionChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        lc_service = get_langchain_service()
        lc_service.provider = provider
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个业务分析师，擅长从业务内容中提取关键目标。
请分析以下业务内容，提取：
1. 核心目标
2. 关键指标
3. 实施建议

输出格式要求：使用清晰的结构化格式。"""),
            ("human", "{business_content}")
        ])
        
        llm = lc_service.llm
        
        chain = prompt | llm | StrOutputParser()
        return chain

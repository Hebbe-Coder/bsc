from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.services.langchain_service import get_langchain_service


class RiskAssessmentChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        lc_service = get_langchain_service()
        lc_service.provider = provider
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个风险评估专家，擅长识别和评估业务风险。
请分析以下业务内容，进行风险评估：
1. 高风险项
2. 中风险项
3. 低风险项
4. 风险监控建议

输出格式要求：使用清晰的结构化格式。"""),
            ("human", "{business_context}")
        ])
        
        llm = lc_service.llm
        
        chain = prompt | llm | StrOutputParser()
        return chain

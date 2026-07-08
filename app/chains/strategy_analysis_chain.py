from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.services.langchain_service import get_langchain_service


class StrategyAnalysisChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        lc_service = get_langchain_service()
        lc_service.provider = provider
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个战略规划专家，擅长SWOT分析和战略规划。
请分析以下业务信息，进行SWOT分析：
1. 优势(S)
2. 劣势(W)
3. 机会(O)
4. 威胁(T)
5. 战略建议

输出格式要求：使用清晰的结构化格式。"""),
            ("human", "{business_info}")
        ])
        
        llm = lc_service.llm
        
        chain = prompt | llm | StrOutputParser()
        return chain

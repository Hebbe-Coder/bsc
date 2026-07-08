from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.services.langchain_service import get_langchain_service


class KpiExtractionChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        lc_service = get_langchain_service()
        lc_service.provider = provider
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个数据分析师，擅长提取和定义关键绩效指标。
请分析以下业务内容，提取：
1. 核心指标（表格形式）
2. 运营指标（表格形式）
3. 预警机制

输出格式要求：使用Markdown表格和列表格式。"""),
            ("human", "{business_content}")
        ])
        
        llm = lc_service.llm
        
        chain = prompt | llm | StrOutputParser()
        return chain

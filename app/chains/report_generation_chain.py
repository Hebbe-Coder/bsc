from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.services.langchain_service import get_langchain_service


class ReportGenerationChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        lc_service = get_langchain_service()
        lc_service.provider = provider
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个商业分析师，擅长撰写专业的业务分析报告。
请根据以下业务内容，生成完整的业务分析报告：
1. 执行摘要
2. 市场分析
3. 业务现状
4. 用户分析
5. 竞争分析
6. 战略建议
7. 实施计划
8. 结论

输出格式要求：使用清晰的结构化格式，包含以上8个章节。"""),
            ("human", "{business_content}")
        ])
        
        llm = lc_service.llm
        
        chain = prompt | llm | StrOutputParser()
        return chain

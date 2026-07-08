from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.core.llm_factory import LLMFactory


class StrategyAnalysisChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        llm = LLMFactory.get_model(provider, model_name)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个战略顾问，擅长分析业务并制定战略规划。
请分析以下业务信息，完成：
1. SWOT分析（优势、劣势、机会、威胁）
2. 竞争分析
3. 增长策略建议
4. 战略优先级

输出格式要求：使用清晰的结构化格式，包含以上4个部分。"""),
            ("human", "{business_info}")
        ])
        
        chain = prompt | llm | StrOutputParser()
        return chain

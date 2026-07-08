from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.core.llm_factory import LLMFactory


class ObjectiveExtractionChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        llm = LLMFactory.get_model(provider, model_name)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个战略分析专家，擅长从业务文档中提取关键目标和KPI。
请从以下业务内容中提取：
1. 业务目标（可量化的目标）
2. 关键结果指标（KPI）
3. 目标值
4. 优先级

输出格式要求：使用结构化列表，包含目标名称、目标值、优先级和描述。"""),
            ("human", "{business_content}")
        ])
        
        chain = prompt | llm | StrOutputParser()
        return chain

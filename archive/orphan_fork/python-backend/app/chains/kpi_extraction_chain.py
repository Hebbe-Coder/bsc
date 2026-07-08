from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.core.llm_factory import LLMFactory


class KpiExtractionChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        llm = LLMFactory.get_model(provider, model_name)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个数据分析师，擅长从业务描述中识别和定义关键绩效指标(KPI)。
请分析以下业务内容，识别并定义：
1. KPI名称
2. 计算方法
3. 目标值
4. 数据来源
5. 频率

输出格式要求：使用表格或结构化列表格式。"""),
            ("human", "{business_content}")
        ])
        
        chain = prompt | llm | StrOutputParser()
        return chain

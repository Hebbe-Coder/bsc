from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.services.langchain_service import get_langchain_service


class ChartGenerationChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        lc_service = get_langchain_service()
        lc_service.provider = provider
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个数据可视化专家，擅长生成ECharts图表配置。
请根据以下数据描述，生成完整的ECharts JSON配置。

输出格式要求：
- 只输出JSON格式，不要包含其他内容
- 包含chartType、title、xAxis、yAxis、series等字段
- 确保JSON格式正确"""),
            ("human", "{data_description}")
        ])
        
        llm = lc_service.llm
        
        chain = prompt | llm | StrOutputParser()
        return chain

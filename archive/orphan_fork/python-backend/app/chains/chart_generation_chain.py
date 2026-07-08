from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.core.llm_factory import LLMFactory


class ChartGenerationChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        llm = LLMFactory.get_model(provider, model_name)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个数据可视化专家，擅长根据数据描述生成图表配置。
请分析以下数据描述，生成ECharts图表配置JSON：
1. 确定最合适的图表类型（柱状图、折线图、饼图等）
2. 生成完整的配置对象，包含数据系列、样式、标签等
3. 确保配置可直接用于ECharts.init().setOption()

输出格式要求：仅输出JSON字符串，不要包含其他文字。"""),
            ("human", "{data_description}")
        ])
        
        chain = prompt | llm | StrOutputParser()
        return chain

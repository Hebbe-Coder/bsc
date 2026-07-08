from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.core.llm_factory import LLMFactory


class RiskAssessmentChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        llm = LLMFactory.get_model(provider, model_name)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个风险管理专家，擅长识别和评估业务风险。
请分析以下业务场景，识别潜在风险并评估：
1. 风险名称和描述
2. 风险等级（critical/high/medium/low）
3. 发生概率
4. 影响范围
5. 应对策略

输出格式要求：使用结构化列表，清晰展示每个风险及其评估信息。"""),
            ("human", "{business_context}")
        ])
        
        chain = prompt | llm | StrOutputParser()
        return chain

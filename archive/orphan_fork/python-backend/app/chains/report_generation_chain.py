from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.core.llm_factory import LLMFactory


class ReportGenerationChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        llm = LLMFactory.get_model(provider, model_name)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个专业的报告撰写专家，擅长撰写业务分析报告。
请根据以下业务内容，生成一份完整的业务分析报告，包含：
1. 执行摘要
2. 业务背景
3. 数据分析
4. 结论和建议

输出格式要求：使用Markdown格式，包含标题、列表、表格等。"""),
            ("human", "{business_content}")
        ])
        
        chain = prompt | llm | StrOutputParser()
        return chain

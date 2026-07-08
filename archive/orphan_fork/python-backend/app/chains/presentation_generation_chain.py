from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence

from app.core.llm_factory import LLMFactory


class PresentationGenerationChain:
    @classmethod
    def create(cls, provider: str = "deepseek", model_name: str = "") -> RunnableSequence:
        llm = LLMFactory.get_model(provider, model_name)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个演示文稿专家，擅长根据业务内容生成PPT幻灯片大纲。
请分析以下业务内容，生成PPT幻灯片结构：
1. 标题页内容
2. 目录结构
3. 每页幻灯片的主题和要点
4. 建议的图表类型

输出格式要求：使用清晰的结构化格式，包含每页的标题和要点列表。"""),
            ("human", "{business_content}")
        ])
        
        chain = prompt | llm | StrOutputParser()
        return chain

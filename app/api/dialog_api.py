"""
Dialog API - 对话式需求确认接口

提供完整的对话式需求确认API：
1. 创建会话
2. 回答问题
3. 获取会话状态
4. 完成会话
5. 获取用户会话列表
6. 删除会话
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

from app.core.dialog_engine import DialogEngine
from app.api.response import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dialog", tags=["Dialog"])


class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    user_id: str = Field(..., description="用户ID")
    input_text: str = Field(..., description="用户输入文本")
    depth: str = Field("medium", description="对话深度：light/medium/deep")
    industry: str = Field("general", description="行业类型")


class AnswerRequest(BaseModel):
    """回答问题请求"""
    answer: str = Field(..., description="用户回答")
    user_id: Optional[str] = Field(None, description="用户ID")


class CompleteSessionRequest(BaseModel):
    """完成会话请求"""
    compile: bool = Field(False, description="是否直接编译")


class RefinePRDRequest(BaseModel):
    """精化PRD请求"""
    max_iterations: int = Field(3, description="最大迭代次数")
    target_score: int = Field(80, description="目标分数")


class AutoOptimizePRDRequest(BaseModel):
    """自动优化PRD请求"""
    target_score: int = Field(80, description="目标分数")


class DialogEngineInstance:
    """对话引擎实例（单例）"""
    _instance = None
    _agent_instance = None
    
    @classmethod
    def get_instance(cls) -> DialogEngine:
        if cls._instance is None:
            cls._instance = DialogEngine()
        return cls._instance
    
    @classmethod
    def get_agent_instance(cls) -> DialogEngine:
        if cls._agent_instance is None:
            cls._agent_instance = DialogEngine(use_agent=True)
        return cls._agent_instance


@router.post("/session", summary="创建对话会话")
async def create_session(req: CreateSessionRequest):
    """
    创建对话会话，开始需求确认流程
    
    参数：
    - user_id: 用户ID
    - input_text: 用户输入的简短描述
    - depth: 对话深度（light/medium/deep）
    - industry: 行业类型（可选，自动检测）
    
    返回：
    - session_id: 会话ID
    - next_question: 第一个问题
    - question_number: 当前问题序号
    - total_questions: 总问题数
    """
    engine = DialogEngineInstance.get_instance()
    
    try:
        result = engine.create_session(req.user_id, req.input_text, req.depth, req.industry)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=ApiResponse.error(result["error"]).dict())
        
        return ApiResponse.ok(result)
    except Exception as e:
        logger.error(f"Failed to create dialog session: {e}")
        raise HTTPException(status_code=500, detail=ApiResponse.error(str(e)).dict())


@router.post("/session/{session_id}/answer", summary="回答问题")
async def answer_question(session_id: str, req: AnswerRequest):
    """
    回答当前问题，继续对话流程
    
    参数：
    - session_id: 会话ID
    - answer: 用户回答
    - user_id: 用户ID（可选）
    
    返回：
    - next_question: 下一个问题（如果还有）
    - status: 会话状态
    - collected_data: 已收集的数据
    """
    engine = DialogEngineInstance.get_instance()
    
    try:
        result = engine.answer_question(session_id, req.answer, req.user_id)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=ApiResponse.error(result["error"], code=404).dict())
        
        return ApiResponse.ok(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to answer question: {e}")
        raise HTTPException(status_code=500, detail=ApiResponse.error(str(e)).dict())


@router.get("/session/{session_id}", summary="获取会话状态")
async def get_session_status(session_id: str):
    """
    获取会话详细状态
    
    参数：
    - session_id: 会话ID
    
    返回：
    - session_id: 会话ID
    - status: 会话状态
    - collected_data: 已收集的数据
    - messages: 对话消息列表
    """
    engine = DialogEngineInstance.get_instance()
    
    try:
        session = engine.get_session_status(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail=ApiResponse.not_found("会话不存在").dict())
        
        return ApiResponse.ok(session)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session status: {e}")
        raise HTTPException(status_code=500, detail=ApiResponse.error(str(e)).dict())


@router.post("/session/{session_id}/complete", summary="完成会话")
async def complete_session(session_id: str, req: CompleteSessionRequest = None):
    """
    完成会话，生成PRD并可选编译
    
    参数：
    - session_id: 会话ID
    - compile: 是否直接编译（默认false）
    
    返回：
    - prd_text: 生成的PRD文本
    - collected_data: 收集的数据
    - business_system: 编译结果（如果compile=true）
    """
    engine = DialogEngineInstance.get_instance()
    compile_flag = req.compile if req else False
    
    try:
        result = engine.complete_session(session_id, compile_flag)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=ApiResponse.error(result["error"], code=404).dict())
        
        return ApiResponse.ok(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to complete session: {e}")
        raise HTTPException(status_code=500, detail=ApiResponse.error(str(e)).dict())


@router.delete("/session/{session_id}", summary="删除会话")
async def delete_session(session_id: str):
    """
    删除对话会话
    
    参数：
    - session_id: 会话ID
    
    返回：
    - success: 是否成功
    """
    engine = DialogEngineInstance.get_instance()
    
    try:
        success = engine.delete_session(session_id)
        
        if success:
            return ApiResponse.ok({"success": True, "message": "会话已删除"})
        else:
            raise HTTPException(status_code=404, detail=ApiResponse.not_found("会话不存在").dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        raise HTTPException(status_code=500, detail=ApiResponse.error(str(e)).dict())


@router.post("/agent/session", summary="创建Agent对话会话")
async def create_agent_session(req: CreateSessionRequest):
    """
    创建Agent对话会话，使用LangChain Agent进行智能对话
    
    参数：
    - user_id: 用户ID
    - input_text: 用户输入的简短描述
    - depth: 对话深度（light/medium/deep）
    - industry: 行业类型（可选，自动检测）
    
    返回：
    - session_id: 会话ID
    - message: 初始响应
    """
    engine = DialogEngineInstance.get_agent_instance()
    
    try:
        result = engine.create_session(req.user_id, req.input_text, req.depth, req.industry)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=ApiResponse.error(result["error"]).dict())
        
        return ApiResponse.ok(result)
    except Exception as e:
        logger.error(f"Failed to create agent session: {e}")
        raise HTTPException(status_code=500, detail=ApiResponse.error(str(e)).dict())


@router.post("/agent/session/{session_id}/chat", summary="Agent对话")
async def agent_chat(session_id: str, req: AnswerRequest):
    """
    与Agent进行智能对话
    
    参数：
    - session_id: 会话ID
    - answer: 用户输入
    - user_id: 用户ID（可选）
    
    返回：
    - response: Agent响应
    - type: 响应类型（question/prd/general）
    - session_id: 会话ID
    """
    engine = DialogEngineInstance.get_agent_instance()
    
    try:
        result = engine.agent_chat(session_id, req.answer, req.user_id)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=ApiResponse.error(result["error"], code=404).dict())
        
        return ApiResponse.ok(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent chat failed: {e}")
        raise HTTPException(status_code=500, detail=ApiResponse.error(str(e)).dict())


@router.get("/sessions/{user_id}", summary="获取用户会话列表")
async def get_user_sessions(user_id: str, limit: int = 10):
    """
    获取用户的对话会话列表
    
    参数：
    - user_id: 用户ID
    - limit: 返回数量限制（默认10）
    
    返回：
    - sessions: 会话列表
    """
    engine = DialogEngineInstance.get_instance()
    
    try:
        sessions = engine.get_user_sessions(user_id, limit)
        return ApiResponse.ok({"sessions": sessions, "count": len(sessions)})
    except Exception as e:
        logger.error(f"Failed to get user sessions: {e}")
        raise HTTPException(status_code=500, detail=ApiResponse.error(str(e)).dict())


@router.post("/quick", summary="快速生成PRD（跳过对话）")
async def quick_generate(req: CreateSessionRequest):
    """
    快速生成PRD，不进行对话确认，直接使用用户输入生成
    
    参数：
    - user_id: 用户ID
    - input_text: 用户输入文本
    - industry: 行业类型
    
    返回：
    - prd_text: 生成的PRD文本
    """
    from app.engines.prd_analyzer import PRDAnalyzer
    from app.services.langchain_service import LangChainService
    from app.core.config import settings
    
    analyzer = PRDAnalyzer()
    analysis = analyzer.analyze(req.input_text)
    
    langchain_service = LangChainService(
        provider=settings.LLM_PROVIDER,
        use_mock=(settings.LLM_PROVIDER == "mock")
    )
    
    prd_text = langchain_service.generate_prd(
        input_text=req.input_text,
        industry=req.industry,
        collected_data={}
    )
    
    if not prd_text or len(prd_text) < 100:
        prd_text = f"""# {req.input_text}产品PRD

## 一、产品概述

本产品是一款面向{analysis["industry"]}领域的业务系统，旨在提升业务效率，优化用户体验，实现数字化转型目标。

## 二、业务目标

根据业务分析，本产品的核心业务目标包括：
- 短期目标（1-3个月）：完成MVP版本上线，验证商业模式
- 中期目标（3-6个月）：获取目标用户，建立产品口碑
- 长期目标（6-12个月）：实现盈利，建立行业影响力

## 三、核心功能模块

### 核心功能模块1
- 功能点1：详细描述功能的价值和作用
- 功能点2：详细描述功能的价值和作用

### 核心功能模块2
- 功能点1：详细描述功能的价值和作用
- 功能点2：详细描述功能的价值和作用

## 四、用户角色与权限

### 管理员
- 职责：系统管理、用户管理、配置管理
- 权限：全部权限

### 普通用户
- 职责：使用系统核心功能
- 权限：只读和操作权限

### 运营人员
- 职责：业务运营、数据监控
- 权限：运营相关权限

## 五、业务流程图

```mermaid
flowchart TD
    A[用户访问] --> B[浏览产品]
    B --> C[选择功能]
    C --> D[完成操作]
    D --> E[获取结果]
```

## 六、非功能需求

### 性能要求
- 响应时间：核心页面<2秒，API<500ms
- QPS：峰值>1000
- 可用性：99.9%

### 安全要求
- 数据加密：传输加密（HTTPS）、存储加密
- 访问控制：基于角色的权限控制
- 日志审计：完整的操作日志记录

### 合规要求
- 数据合规：符合行业数据保护规范
- 隐私保护：用户隐私数据保护措施

## 七、成功标准

### 业务指标
- 用户增长：月活用户增长率>20%
- 转化率：注册转化率>10%
- 留存率：7日留存>40%

### 技术指标
- 系统可用性：>99.9%
- 响应时间：<2秒
- 错误率：<0.1%

### 用户指标
- 用户满意度：>4.5分（5分制）
- NPS评分：>50

## 八、项目里程碑

### Phase 1：基础功能（第1-4周）
- 完成核心功能开发
- 内部测试通过
- 目标：MVP版本上线

### Phase 2：高级功能（第5-8周）
- 完成高级功能开发
- 性能优化
- 目标：功能完善版本上线

### Phase 3：优化迭代（第9-12周）
- 用户反馈收集和分析
- Bug修复和体验优化
- 目标：稳定运营版本

## 九、分析建议

{chr(10).join([f"- {r['suggestion']}" for r in analysis["recommendations"]])}"""
    
    return ApiResponse.ok({
        "prd_text": prd_text,
        "analysis": analysis,
    })


@router.post("/session/{session_id}/prd/score", summary="评估PRD质量")
async def score_prd_quality(session_id: str):
    """
    评估PRD文档质量，使用两层评分体系（规则启发式+LLM评估）
    
    参数：
    - session_id: 会话ID
    
    返回：
    - overall_score: 综合评分
    - quality_level: 质量等级
    - is_passed: 是否合格
    - dimensions: 各维度评分详情
    - suggestions: 改进建议
    """
    engine = DialogEngineInstance.get_instance()
    
    try:
        result = engine.score_prd_quality(session_id)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=ApiResponse.error(result["error"], code=404).dict())
        
        return ApiResponse.ok(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to score PRD quality: {e}")
        raise HTTPException(status_code=500, detail=ApiResponse.error(str(e)).dict())


@router.post("/session/{session_id}/prd/refine", summary="精化PRD")
async def refine_prd(session_id: str, req: RefinePRDRequest):
    """
    多轮迭代精化PRD文档，提升质量评分
    
    参数：
    - session_id: 会话ID
    - max_iterations: 最大迭代次数（默认3次）
    - target_score: 目标分数（默认80分）
    
    返回：
    - final_prd: 优化后的PRD
    - iterations: 实际迭代次数
    - initial_score: 初始评分
    - final_score: 最终评分
    - delta: 评分提升幅度
    - steps: 迭代步骤详情
    """
    engine = DialogEngineInstance.get_instance()
    
    try:
        result = engine.refine_prd(session_id, req.max_iterations, req.target_score)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=ApiResponse.error(result["error"], code=404).dict())
        
        return ApiResponse.ok(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refine PRD: {e}")
        raise HTTPException(status_code=500, detail=ApiResponse.error(str(e)).dict())


@router.post("/session/{session_id}/prd/auto-optimize", summary="自动优化PRD")
async def auto_optimize_prd(session_id: str, req: AutoOptimizePRDRequest):
    """
    自动优化PRD至目标分数，智能计算迭代次数
    
    参数：
    - session_id: 会话ID
    - target_score: 目标分数（默认80分）
    
    返回：
    - final_prd: 优化后的PRD
    - iterations: 实际迭代次数
    - initial_score: 初始评分
    - final_score: 最终评分
    - delta: 评分提升幅度
    """
    engine = DialogEngineInstance.get_instance()
    
    try:
        result = engine.auto_optimize_prd(session_id, req.target_score)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=ApiResponse.error(result["error"], code=404).dict())
        
        return ApiResponse.ok(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to auto-optimize PRD: {e}")
        raise HTTPException(status_code=500, detail=ApiResponse.error(str(e)).dict())


__all__ = ["router"]

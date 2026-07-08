"""
Recommendation Engine - 智能推荐引擎

基于历史数据和行业模式提供智能推荐，支持：
1. 相似项目推荐：基于PRD内容相似度推荐优化方案
2. 行业最佳实践推荐：基于行业模式库推荐通用优化方案
3. 个性化推荐：基于用户历史行为推荐
4. 推荐置信度评估：计算推荐的置信度得分

推荐类型：
- optimization: 优化建议
- template: 模板推荐
- workflow: 流程优化
- risk_mitigation: 风险应对
- kpi: KPI指标推荐
"""
import json
import uuid
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.database import get_database_backend

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """智能推荐引擎"""
    
    def __init__(self):
        self._backend = get_database_backend()
    
    def record_compile(self, prd_content: str, business_domain: str, 
                      industry: str, result_summary: str, execution_time_ms: int,
                      success: bool = True, error_message: str = "", 
                      template_id: str = "", metadata: Dict[str, Any] = None):
        """记录编译历史"""
        record_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        try:
            self._backend.execute(
                """
                INSERT INTO compile_history 
                (id, prd_content, business_domain, industry, template_id, 
                 result_summary, execution_time_ms, success, error_message, 
                 created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id, prd_content[:500], business_domain, industry, template_id,
                    result_summary[:500], execution_time_ms, 1 if success else 0, error_message[:200],
                    now, json.dumps(metadata or {}, ensure_ascii=False)
                )
            )
            self._backend.commit()
            logger.info(f"Recorded compile history: {record_id}")
            return record_id
        except Exception as e:
            self._backend.rollback()
            logger.error(f"Failed to record compile history: {e}")
            return None
    
    def analyze_similar_projects(self, prd_content: str, industry: str, 
                                top_n: int = 5) -> List[Dict[str, Any]]:
        """分析相似项目，提取优化建议"""
        try:
            cursor = self._backend.execute(
                """
                SELECT id, business_domain, industry, result_summary, metadata
                FROM compile_history 
                WHERE industry = ? AND success = 1
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (industry, top_n)
            )
            similar_projects = self._backend.rows_to_list(cursor)
            self._backend.close()
            
            recommendations = []
            for project in similar_projects:
                metadata = {}
                try:
                    metadata = json.loads(project.get("metadata", "{}"))
                except json.JSONDecodeError:
                    pass
                
                optimization = metadata.get("optimization", {})
                recommendations.extend(optimization.get("recommendations", []))
            
            return recommendations[:top_n]
        except Exception as e:
            logger.error(f"Failed to analyze similar projects: {e}")
            return []
    
    def get_industry_patterns(self, industry: str, pattern_type: str = "optimization",
                             top_n: int = 10) -> List[Dict[str, Any]]:
        """获取行业最佳实践模式"""
        try:
            cursor = self._backend.execute(
                """
                SELECT pattern_name, pattern_content, frequency, avg_improvement
                FROM industry_patterns 
                WHERE industry = ? AND pattern_type = ?
                ORDER BY frequency DESC, avg_improvement DESC
                LIMIT ?
                """,
                (industry, pattern_type, top_n)
            )
            patterns = self._backend.rows_to_list(cursor)
            self._backend.close()
            
            return patterns
        except Exception as e:
            logger.error(f"Failed to get industry patterns: {e}")
            return []
    
    def generate_recommendations(self, prd_content: str, business_domain: str, 
                                industry: str, template_id: str = "",
                                business_system: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        生成综合推荐
        
        推荐来源：
        1. 行业模式库（最高优先级）
        2. 相似项目历史（中等优先级）
        3. 业务系统分析结果（基础优先级）
        """
        recommendations = []
        
        industry_patterns = self.get_industry_patterns(industry)
        for pattern in industry_patterns:
            recommendations.append({
                "type": "industry_pattern",
                "title": pattern["pattern_name"],
                "content": pattern["pattern_content"],
                "confidence": min(0.9, 0.7 + pattern["frequency"] * 0.02),
                "source": f"行业最佳实践 - {industry}",
                "priority": "high",
            })
        
        similar_recs = self.analyze_similar_projects(prd_content, industry)
        for rec in similar_recs[:5]:
            if isinstance(rec, dict):
                recommendations.append({
                    "type": "similar_project",
                    "title": rec.get("title", "优化建议"),
                    "content": rec.get("content", str(rec)),
                    "confidence": 0.6,
                    "source": "相似项目经验",
                    "priority": "medium",
                })
            elif isinstance(rec, str):
                recommendations.append({
                    "type": "similar_project",
                    "title": "优化建议",
                    "content": rec,
                    "confidence": 0.5,
                    "source": "相似项目经验",
                    "priority": "medium",
                })
        
        if business_system:
            optimization = business_system.get("optimization", {})
            for rec in optimization.get("recommendations", []):
                recommendations.append({
                    "type": "analysis",
                    "title": rec.get("title", "优化建议"),
                    "content": rec.get("content", str(rec)),
                    "confidence": 0.75,
                    "source": "智能分析结果",
                    "priority": "high",
                })
        
        recommendations.sort(key=lambda x: (x["confidence"], x["priority"] == "high"), reverse=True)
        
        return recommendations[:10]
    
    def save_recommendation(self, project_id: str, rec_type: str, content: str,
                           confidence: float, source: str = "system") -> str:
        """保存推荐结果"""
        rec_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        try:
            self._backend.execute(
                """
                INSERT INTO recommendations 
                (id, project_id, type, content, confidence, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (rec_id, project_id, rec_type, content, confidence, source, now)
            )
            self._backend.commit()
            logger.info(f"Saved recommendation: {rec_id}")
            return rec_id
        except Exception as e:
            self._backend.rollback()
            logger.error(f"Failed to save recommendation: {e}")
            return None
    
    def mark_recommendation_applied(self, rec_id: str):
        """标记推荐已应用"""
        now = datetime.now().isoformat()
        
        try:
            self._backend.execute(
                """
                UPDATE recommendations 
                SET applied = 1, applied_at = ?
                WHERE id = ?
                """,
                (now, rec_id)
            )
            self._backend.commit()
            logger.info(f"Marked recommendation applied: {rec_id}")
        except Exception as e:
            self._backend.rollback()
            logger.error(f"Failed to mark recommendation applied: {e}")
    
    def get_project_recommendations(self, project_id: str, 
                                    include_applied: bool = False) -> List[Dict[str, Any]]:
        """获取项目的推荐列表"""
        try:
            query = """
                SELECT id, type, content, confidence, source, applied, created_at, applied_at
                FROM recommendations 
                WHERE project_id = ?
            """
            params = [project_id]
            
            if not include_applied:
                query += " AND applied = 0"
            
            query += " ORDER BY confidence DESC, created_at DESC"
            
            cursor = self._backend.execute(query, tuple(params))
            recs = self._backend.rows_to_list(cursor)
            self._backend.close()
            
            return recs
        except Exception as e:
            logger.error(f"Failed to get project recommendations: {e}")
            return []
    
    def add_industry_pattern(self, industry: str, pattern_type: str, 
                            pattern_name: str, pattern_content: str):
        """添加行业模式"""
        pattern_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        try:
            cursor = self._backend.execute(
                "SELECT id FROM industry_patterns WHERE industry = ? AND pattern_name = ?",
                (industry, pattern_name)
            )
            existing = cursor.fetchone()
            
            if existing:
                self._backend.execute(
                    """
                    UPDATE industry_patterns 
                    SET pattern_content = ?, frequency = frequency + 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (pattern_content, now, existing["id"])
                )
            else:
                self._backend.execute(
                    """
                    INSERT INTO industry_patterns 
                    (id, industry, pattern_type, pattern_name, pattern_content, 
                     frequency, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (pattern_id, industry, pattern_type, pattern_name, pattern_content, now, now)
                )
            
            self._backend.commit()
            logger.info(f"Added/updated industry pattern: {pattern_name}")
        except Exception as e:
            self._backend.rollback()
            logger.error(f"Failed to add industry pattern: {e}")
    
    def get_compile_history(self, industry: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """获取编译历史"""
        try:
            query = """
                SELECT id, business_domain, industry, result_summary, 
                       execution_time_ms, success, created_at
                FROM compile_history 
            """
            params = []
            
            if industry:
                query += " WHERE industry = ?"
                params.append(industry)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = self._backend.execute(query, tuple(params))
            history = self._backend.rows_to_list(cursor)
            self._backend.close()
            
            return history
        except Exception as e:
            logger.error(f"Failed to get compile history: {e}")
            return []
    
    def get_compile_stats(self, industry: str = None) -> Dict[str, Any]:
        """获取编译统计信息"""
        try:
            query = """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                    AVG(execution_time_ms) as avg_time_ms,
                    MIN(execution_time_ms) as min_time_ms,
                    MAX(execution_time_ms) as max_time_ms
                FROM compile_history
            """
            params = []
            
            if industry:
                query += " WHERE industry = ?"
                params.append(industry)
            
            cursor = self._backend.execute(query, tuple(params))
            stats = self._backend.row_to_dict(cursor.fetchone())
            self._backend.close()
            
            success_rate = (stats["success_count"] / stats["total"] * 100) if stats["total"] > 0 else 0
            
            return {
                "total_compiles": stats["total"],
                "success_count": stats["success_count"],
                "success_rate": round(success_rate, 2),
                "avg_time_ms": round(stats["avg_time_ms"], 0) if stats["avg_time_ms"] else 0,
                "min_time_ms": stats["min_time_ms"] or 0,
                "max_time_ms": stats["max_time_ms"] or 0,
            }
        except Exception as e:
            logger.error(f"Failed to get compile stats: {e}")
            return {}


_recommendation_engine: Optional[RecommendationEngine] = None


def get_recommendation_engine() -> RecommendationEngine:
    """获取推荐引擎实例"""
    global _recommendation_engine
    if _recommendation_engine is None:
        _recommendation_engine = RecommendationEngine()
    return _recommendation_engine

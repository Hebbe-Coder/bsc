"""测试专业级PPT和HTML导出"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from exporters import export_professional, export_with_theme, export_for_industry, export_html, export_html_dark

test_data = {
    "business_system": {
        "metadata": {
            "title": "零售电商订单管理系统",
            "industry": "retail",
        },
        "business_domain": "零售电商",
        "objective": "构建一套高效的订单管理系统，实现订单全生命周期管理，提升运营效率和客户体验",
        "description": "该系统将涵盖订单创建、支付处理、库存管理、物流追踪、售后服务等核心业务流程，支持多渠道订单统一管理",
        "tech_stack": "FastAPI + Python + Redis + PostgreSQL",
        "modules": [
            {"name": "订单管理模块", "description": "处理订单创建、修改、取消等操作", "depends_on": ["用户模块", "商品模块"]},
            {"name": "支付模块", "description": "集成多种支付方式，处理支付流程", "depends_on": ["订单模块"]},
            {"name": "库存模块", "description": "实时库存管理，库存预警", "depends_on": ["商品模块"]},
            {"name": "物流模块", "description": "订单配送追踪，物流信息同步", "depends_on": ["订单模块"]},
            {"name": "售后模块", "description": "处理退换货申请，售后服务", "depends_on": ["订单模块"]},
            {"name": "数据分析模块", "description": "订单数据分析，业务报表", "depends_on": ["订单模块", "库存模块"]},
        ],
        "workflow": [
            {"name": "用户下单", "owner": "客户", "sla_hours": 24, "next": ["订单审核"]},
            {"name": "订单审核", "owner": "审核员", "sla_hours": 1, "next": ["库存检查"]},
            {"name": "库存检查", "owner": "系统", "sla_hours": 0.5, "next": ["支付处理"]},
            {"name": "支付处理", "owner": "支付系统", "sla_hours": 0.25, "next": ["发货"]},
            {"name": "发货", "owner": "仓库", "sla_hours": 4, "next": ["配送"]},
            {"name": "配送", "owner": "物流商", "sla_hours": 48, "next": ["签收"]},
            {"name": "签收", "owner": "客户", "sla_hours": 72, "next": ["完成"]},
            {"name": "完成", "owner": "系统", "next": []},
        ],
        "kpi": [
            {"name": "订单处理时长", "target": "2小时", "formula": "完成时间 - 创建时间"},
            {"name": "订单准确率", "target": "99.5%", "formula": "准确订单数 / 总订单数"},
            {"name": "库存周转率", "target": "8次/月", "formula": "出库量 / 平均库存"},
            {"name": "客户满意度", "target": "95%", "formula": "满意评价数 / 总评价数"},
            {"name": "退货率", "target": "<3%", "formula": "退货订单数 / 总订单数"},
            {"name": "支付成功率", "target": "99%", "formula": "成功支付数 / 支付请求数"},
        ],
        "risk": [
            {"name": "库存不足导致超卖", "severity": "critical", "score": 9, "description": "高并发场景下库存扣减不一致", "mitigation": "使用分布式锁，预扣库存机制"},
            {"name": "支付超时", "severity": "high", "score": 7, "description": "第三方支付接口响应慢", "mitigation": "异步处理，超时重试"},
            {"name": "物流信息延迟", "severity": "medium", "score": 5, "description": "物流商数据同步延迟", "mitigation": "定时拉取，增量更新"},
            {"name": "订单数据一致性", "severity": "high", "score": 8, "description": "多渠道订单数据不一致", "mitigation": "统一数据中台，实时同步"},
            {"name": "系统性能瓶颈", "severity": "medium", "score": 6, "description": "大促期间系统响应慢", "mitigation": "缓存策略，水平扩展"},
            {"name": "安全风险", "severity": "medium", "score": 5, "description": "订单数据泄露风险", "mitigation": "数据加密，访问控制"},
        ],
        "strategy": {
            "recommendations": [
                {"title": "引入分布式锁", "investment": 50000, "annual_savings": 300000},
                {"title": "异步支付处理", "investment": 30000, "annual_savings": 200000},
                {"title": "智能库存预警", "investment": 40000, "annual_savings": 250000},
                {"title": "实时数据同步", "investment": 60000, "annual_savings": 350000},
            ],
            "strategic_path": [
                {"phase": "第一阶段", "theme": "基础架构", "timeline": "0-4周", "items": ["核心模块开发", "数据库设计", "API接口"]},
                {"phase": "第二阶段", "theme": "核心功能", "timeline": "4-8周", "items": ["订单流程", "支付集成", "库存管理"]},
                {"phase": "第三阶段", "theme": "优化完善", "timeline": "8-12周", "items": ["性能优化", "安全加固", "数据分析"]},
            ],
        },
        "current_processing_time": "4.2小时",
        "target_processing_time": "1.8小时",
        "processing_improvement": "-57%",
        "current_manual_review": "100%",
        "target_manual_review": "40%",
        "review_improvement": "-60%",
        "current_error_rate": "3.2%",
        "target_error_rate": "1.1%",
        "error_improvement": "-65%",
        "current_utilization": "68%",
        "target_utilization": "92%",
        "utilization_improvement": "+24%",
    }
}

print("=" * 60)
print("测试专业级PPT导出")
print("=" * 60)

try:
    ppt_path = export_professional(test_data, theme='business')
    print(f"✅ PPT导出成功: {ppt_path}")
    
    ppt_tech_path = export_with_theme(test_data, theme='tech')
    print(f"✅ 科技主题PPT导出成功: {ppt_tech_path}")
    
    ppt_retail_path = export_for_industry(test_data, industry='retail')
    print(f"✅ 零售行业PPT导出成功: {ppt_retail_path}")
except Exception as e:
    print(f"❌ PPT导出失败: {e}")

print("\n" + "=" * 60)
print("测试专业级HTML导出")
print("=" * 60)

try:
    html_content = export_html(test_data)
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "report_light.html")
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"✅ HTML导出成功: {html_path}")
    
    html_dark_content = export_html_dark(test_data)
    html_dark_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "report_dark.html")
    with open(html_dark_path, 'w', encoding='utf-8') as f:
        f.write(html_dark_content)
    print(f"✅ 深色主题HTML导出成功: {html_dark_path}")
except Exception as e:
    print(f"❌ HTML导出失败: {e}")

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)
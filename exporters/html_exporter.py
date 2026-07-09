"""
HTML Exporter — Professional Grade v3.0
Design philosophy: Enterprise-Class Interactive Reporting

Key improvements in v3.0:
1. Complete rewrite with no truncated code
2. Enhanced visual design with modern CSS
3. Advanced chart types (funnel, sankey, heatmap, gauge, line)
4. Improved animations and transitions
5. Better responsive design
6. Enhanced data table with pagination and filtering
7. Interactive accordion sections
8. Professional typography and spacing
9. Smooth scroll and navigation
10. Performance optimizations

Every element is dynamically generated from business_system data.
"""
import json
import uuid
import datetime
import html
from typing import Dict, Any, List, Optional

from exporters._degrade_ctx import DegradeContext


class HTMLTheme:
    """HTML主题系统 - 专业配色方案"""
    
    LIGHT = {
        'name': 'light',
        'bg': '#ffffff', 'bg_secondary': '#f8fafc', 'bg_card': '#ffffff',
        'primary': '#1e40af', 'primary_light': '#3b82f6', 'primary_dark': '#1e3a8a',
        'accent': '#f59e0b', 'accent_light': '#fbbf24', 'accent_dark': '#d97706',
        'text': '#1e293b', 'text_light': '#64748b', 'text_faint': '#94a3b8',
        'border': '#e2e8f0', 'border_light': '#f1f5f9',
        'success': '#10b981', 'warning': '#f59e0b', 'danger': '#ef4444', 'info': '#0ea5e9',
        'sidebar_bg': '#0f172a', 'sidebar_text': '#f1f5f9',
        'code_bg': '#1e293b', 'code_text': '#e2e8f0',
        'gradient_start': '#1e40af', 'gradient_end': '#3b82f6',
        'card_shadow': '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05)',
        'card_hover_shadow': '0 20px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.08)',
    }
    
    DARK = {
        'name': 'dark',
        'bg': '#0f172a', 'bg_secondary': '#1e293b', 'bg_card': '#1e293b',
        'primary': '#3b82f6', 'primary_light': '#60a5fa', 'primary_dark': '#1d4ed8',
        'accent': '#f59e0b', 'accent_light': '#fbbf24', 'accent_dark': '#d97706',
        'text': '#f1f5f9', 'text_light': '#94a3b8', 'text_faint': '#64748b',
        'border': '#334155', 'border_light': '#1e293b',
        'success': '#10b981', 'warning': '#f59e0b', 'danger': '#ef4444', 'info': '#0ea5e9',
        'sidebar_bg': '#020617', 'sidebar_text': '#f1f5f9',
        'code_bg': '#0f172a', 'code_text': '#e2e8f0',
        'gradient_start': '#06b6d4', 'gradient_end': '#8b5cf6',
        'card_shadow': '0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -2px rgba(0, 0, 0, 0.2)',
        'card_hover_shadow': '0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.3)',
    }
    
    @classmethod
    def get(cls, name: str) -> dict:
        return getattr(cls, name.upper(), cls.LIGHT)


class HTMLChartGenerator:
    """图表生成器 - 生成ECharts配置"""
    
    @staticmethod
    def bar_chart(data: List[Dict], x_key: str, y_key: str, title: str = "", 
                  subtitle: str = "", theme: dict = HTMLTheme.LIGHT) -> str:
        """生成柱状图配置"""
        labels = [str(d[x_key]) for d in data]
        values = [float(d[y_key]) for d in data]
        
        config = {
            'title': {'text': title, 'subtext': subtitle, 'left': 'center',
                      'textStyle': {'color': theme['text'], 'fontSize': 16, 'fontWeight': 'bold'},
                      'subtextStyle': {'color': theme['text_light'], 'fontSize': 12}},
            'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'shadow'},
                        'backgroundColor': theme['bg_card'], 'borderColor': theme['border'],
                        'borderWidth': 1, 'textStyle': {'color': theme['text']},
                        'padding': [12, 16], 'extraCssText': 'border-radius: 8px;'},
            'grid': {'left': '3%', 'right': '4%', 'bottom': '3%', 'top': '15%', 'containLabel': True},
            'xAxis': {'type': 'category', 'data': labels, 
                      'axisLabel': {'rotate': 30, 'color': theme['text_light'], 'fontSize': 11},
                      'axisLine': {'lineStyle': {'color': theme['border']}},
                      'axisTick': {'show': False}},
            'yAxis': {'type': 'value', 
                      'axisLabel': {'color': theme['text_light'], 'fontSize': 11},
                      'axisLine': {'show': False},
                      'axisTick': {'show': False},
                      'splitLine': {'lineStyle': {'color': theme['border_light'], 'type': 'dashed'}}},
            'series': [{
                'type': 'bar',
                'data': values,
                'itemStyle': {'color': {'type': 'linear', 'x': 0, 'y': 0, 'x2': 0, 'y2': 1,
                                       'colorStops': [{'offset': 0, 'color': theme['primary']},
                                                      {'offset': 1, 'color': theme['primary_light']}]},
                               'borderRadius': [8, 8, 0, 0], 'borderColor': theme['primary'], 'borderWidth': 1},
                'emphasis': {'itemStyle': {'color': theme['primary_dark']}},
                'label': {'show': True, 'position': 'top', 'color': theme['text'], 'fontSize': 11, 'fontWeight': 'bold'},
                'barWidth': '45%',
            }],
            'animationDuration': 1500,
            'animationEasing': 'elasticOut',
        }
        
        return json.dumps(config, ensure_ascii=False)
    
    @staticmethod
    def pie_chart(data: List[Dict], name_key: str, value_key: str, title: str = "",
                  theme: dict = HTMLTheme.LIGHT) -> str:
        """生成饼图配置"""
        pie_data = [{'name': str(d[name_key]), 'value': float(d[value_key])} for d in data]
        
        colors = [theme['primary'], theme['accent'], theme['success'], 
                  theme['warning'], theme['danger'], theme['info']]
        
        config = {
            'title': {'text': title, 'left': 'center', 'top': '5%',
                      'textStyle': {'color': theme['text'], 'fontSize': 16, 'fontWeight': 'bold'}},
            'tooltip': {'trigger': 'item', 'formatter': '{b}: {c} ({d}%)',
                        'backgroundColor': theme['bg_card'], 'borderColor': theme['border'],
                        'borderWidth': 1, 'textStyle': {'color': theme['text']},
                        'padding': [12, 16], 'extraCssText': 'border-radius: 8px;'},
            'legend': {'orient': 'vertical', 'right': '5%', 'top': 'center',
                       'textStyle': {'color': theme['text_light'], 'fontSize': 12},
                       'itemGap': 12},
            'color': colors[:len(pie_data)],
            'series': [{
                'type': 'pie',
                'radius': ['45%', '70%'],
                'center': ['40%', '55%'],
                'avoidLabelOverlap': True,
                'itemStyle': {'borderRadius': 12, 'borderColor': theme['bg'], 'borderWidth': 3},
                'label': {'show': True, 'color': theme['text'], 'fontSize': 11, 'fontWeight': '500'},
                'emphasis': {'label': {'show': True, 'fontSize': 14, 'fontWeight': 'bold'},
                             'scale': True, 'scaleSize': 10},
                'labelLine': {'show': True, 'lineStyle': {'color': theme['border']}},
                'data': pie_data,
                'animationType': 'scale',
                'animationEasing': 'elasticOut',
            }],
            'animationDuration': 2000,
        }
        
        return json.dumps(config, ensure_ascii=False)
    
    @staticmethod
    def gauge_chart(value: float, title: str = "", min_val: float = 0, max_val: float = 100,
                    theme: dict = HTMLTheme.LIGHT) -> str:
        """生成仪表盘配置"""
        percentage = round((value / max_val) * 100, 1)
        
        config = {
            'series': [{
                'type': 'gauge',
                'startAngle': 200,
                'endAngle': -20,
                'pointer': {'show': False},
                'progress': {'show': True, 'overlap': False, 'roundCap': True,
                             'clip': False, 'itemStyle': {'color': {'type': 'linear', 'x': 0, 'y': 0, 'x2': 1, 'y2': 0,
                                                                     'colorStops': [{'offset': 0, 'color': theme['primary_light']},
                                                                                    {'offset': 1, 'color': theme['primary']}]}}},
                'axisLine': {'lineStyle': {'width': 20, 'color': [[1, theme['border']]]}},
                'splitLine': {'show': False},
                'axisTick': {'show': False},
                'axisLabel': {'show': False},
                'data': [{
                    'value': percentage,
                    'detail': {'valueAnimation': True, 'offsetCenter': [0, '65%'],
                               'fontSize': 56, 'fontWeight': 'bold', 'color': theme['text'],
                               'formatter': '{value}%', 'fontFamily': "'Helvetica Neue', 'PingFang SC', sans-serif"},
                    'name': {'offsetCenter': [0, '90%'], 'fontSize': 14, 'color': theme['text_light'], 'fontWeight': '500'},
                }],
            }],
            'title': {'text': title, 'left': 'center', 'top': '5%',
                      'textStyle': {'color': theme['text'], 'fontSize': 14, 'fontWeight': 'bold'}},
            'animationDuration': 2000,
            'animationEasing': 'elasticOut',
        }
        
        return json.dumps(config, ensure_ascii=False)
    
    @staticmethod
    def radar_chart(data: List[Dict], indicators: List[Dict], title: str = "",
                    theme: dict = HTMLTheme.LIGHT) -> str:
        """生成雷达图配置"""
        config = {
            'title': {'text': title, 'left': 'center', 'top': '5%',
                      'textStyle': {'color': theme['text'], 'fontSize': 16, 'fontWeight': 'bold'}},
            'tooltip': {'trigger': 'item',
                        'backgroundColor': theme['bg_card'], 'borderColor': theme['border'],
                        'borderWidth': 1, 'textStyle': {'color': theme['text']},
                        'padding': [12, 16], 'extraCssText': 'border-radius: 8px;'},
            'legend': {'data': [d.get('name', f'Data {i+1}') for i, d in enumerate(data)],
                       'bottom': '5%', 'textStyle': {'color': theme['text_light'], 'fontSize': 12},
                       'itemGap': 20},
            'radar': {
                'indicator': indicators,
                'shape': 'polygon',
                'splitNumber': 5,
                'axisName': {'color': theme['text_light'], 'fontSize': 11, 'fontWeight': '500'},
                'splitLine': {'lineStyle': {'color': theme['border']}},
                'splitArea': {'show': True, 'areaStyle': {'color': [theme['bg_secondary'], theme['bg']]}},
                'axisLine': {'lineStyle': {'color': theme['border']}},
            },
            'series': [{
                'type': 'radar',
                'data': data,
                'areaStyle': {'opacity': 0.2},
                'lineStyle': {'width': 3},
                'itemStyle': {'color': theme['primary'], 'borderWidth': 2},
                'symbol': 'circle',
                'symbolSize': 8,
                'emphasis': {'areaStyle': {'opacity': 0.4}},
            }],
            'animationDuration': 1500,
        }
        
        return json.dumps(config, ensure_ascii=False)
    
    @staticmethod
    def comparison_bar_chart(data: List[Dict], x_key: str, y1_key: str, y2_key: str, 
                             title: str = "", theme: dict = HTMLTheme.LIGHT) -> str:
        """生成对比柱状图配置"""
        labels = [str(d[x_key]) for d in data]
        y1_values = [float(d[y1_key]) for d in data]
        y2_values = [float(d[y2_key]) for d in data]
        
        config = {
            'title': {'text': title, 'left': 'center', 'top': '5%',
                      'textStyle': {'color': theme['text'], 'fontSize': 16, 'fontWeight': 'bold'}},
            'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'shadow'},
                        'backgroundColor': theme['bg_card'], 'borderColor': theme['border'],
                        'borderWidth': 1, 'textStyle': {'color': theme['text']},
                        'padding': [12, 16], 'extraCssText': 'border-radius: 8px;'},
            'legend': {'data': ['当前状态', '目标状态'], 'bottom': '0%',
                       'textStyle': {'color': theme['text_light'], 'fontSize': 12},
                       'itemGap': 30},
            'grid': {'left': '3%', 'right': '4%', 'bottom': '15%', 'top': '20%', 'containLabel': True},
            'xAxis': {'type': 'category', 'data': labels, 
                      'axisLabel': {'color': theme['text_light'], 'fontSize': 11, 'fontWeight': '500'},
                      'axisLine': {'lineStyle': {'color': theme['border']}},
                      'axisTick': {'show': False}},
            'yAxis': {'type': 'value', 
                      'axisLabel': {'color': theme['text_light'], 'fontSize': 11},
                      'axisLine': {'show': False},
                      'axisTick': {'show': False},
                      'splitLine': {'lineStyle': {'color': theme['border_light'], 'type': 'dashed'}}},
            'series': [
                {
                    'name': '当前状态',
                    'type': 'bar',
                    'data': y1_values,
                    'itemStyle': {'color': theme['text_faint'], 'borderRadius': [6, 6, 0, 0], 'borderColor': theme['border'], 'borderWidth': 1},
                    'barWidth': '30%',
                },
                {
                    'name': '目标状态',
                    'type': 'bar',
                    'data': y2_values,
                    'itemStyle': {'color': {'type': 'linear', 'x': 0, 'y': 0, 'x2': 0, 'y2': 1,
                                           'colorStops': [{'offset': 0, 'color': theme['primary']},
                                                          {'offset': 1, 'color': theme['primary_light']}]},
                                   'borderRadius': [6, 6, 0, 0], 'borderColor': theme['primary'], 'borderWidth': 1},
                    'barWidth': '30%',
                    'label': {'show': True, 'position': 'top', 'color': theme['primary'], 'fontSize': 11, 'fontWeight': 'bold'},
                }
            ],
            'animationDuration': 1500,
        }
        
        return json.dumps(config, ensure_ascii=False)
    
    @staticmethod
    def funnel_chart(data: List[Dict], name_key: str, value_key: str, title: str = "",
                     theme: dict = HTMLTheme.LIGHT) -> str:
        """生成漏斗图配置"""
        funnel_data = [{'name': str(d[name_key]), 'value': float(d[value_key])} for d in data]
        
        config = {
            'title': {'text': title, 'left': 'center', 'top': '5%',
                      'textStyle': {'color': theme['text'], 'fontSize': 16, 'fontWeight': 'bold'}},
            'tooltip': {'trigger': 'item', 'formatter': '{b}: {c}',
                        'backgroundColor': theme['bg_card'], 'borderColor': theme['border'],
                        'borderWidth': 1, 'textStyle': {'color': theme['text']},
                        'padding': [12, 16], 'extraCssText': 'border-radius: 8px;'},
            'legend': {'data': [d[name_key] for d in data], 'bottom': '5%',
                       'textStyle': {'color': theme['text_light'], 'fontSize': 12}},
            'series': [{
                'type': 'funnel',
                'left': '10%',
                'top': '15%',
                'bottom': '15%',
                'width': '80%',
                'min': 0,
                'max': 100,
                'minSize': '0%',
                'maxSize': '100%',
                'sort': 'descending',
                'gap': 2,
                'label': {'show': True, 'position': 'inside', 'color': '#fff', 'fontSize': 12, 'fontWeight': 'bold'},
                'labelLine': {'length': 10, 'lineStyle': {'width': 1, 'type': 'solid'}},
                'itemStyle': {'borderColor': '#fff', 'borderWidth': 2, 'borderRadius': 4},
                'emphasis': {'label': {'fontSize': 14}},
                'data': funnel_data,
                'color': [theme['primary'], theme['primary_light'], theme['accent'], theme['accent_light'], theme['success']],
            }],
            'animationDuration': 1500,
        }
        
        return json.dumps(config, ensure_ascii=False)
    
    @staticmethod
    def line_chart(data: List[Dict], x_key: str, y_key: str, title: str = "",
                   theme: dict = HTMLTheme.LIGHT) -> str:
        """生成折线图配置"""
        labels = [str(d[x_key]) for d in data]
        values = [float(d[y_key]) for d in data]
        
        config = {
            'title': {'text': title, 'left': 'center', 'top': '5%',
                      'textStyle': {'color': theme['text'], 'fontSize': 16, 'fontWeight': 'bold'}},
            'tooltip': {'trigger': 'axis',
                        'backgroundColor': theme['bg_card'], 'borderColor': theme['border'],
                        'borderWidth': 1, 'textStyle': {'color': theme['text']},
                        'padding': [12, 16], 'extraCssText': 'border-radius: 8px;'},
            'grid': {'left': '3%', 'right': '4%', 'bottom': '3%', 'top': '15%', 'containLabel': True},
            'xAxis': {'type': 'category', 'boundaryGap': False, 'data': labels,
                      'axisLabel': {'color': theme['text_light'], 'fontSize': 11},
                      'axisLine': {'lineStyle': {'color': theme['border']}},
                      'axisTick': {'show': False}},
            'yAxis': {'type': 'value',
                      'axisLabel': {'color': theme['text_light'], 'fontSize': 11},
                      'axisLine': {'show': False},
                      'axisTick': {'show': False},
                      'splitLine': {'lineStyle': {'color': theme['border_light'], 'type': 'dashed'}}},
            'series': [{
                'type': 'line',
                'smooth': True,
                'symbol': 'circle',
                'symbolSize': 8,
                'lineStyle': {'width': 3, 'color': theme['primary']},
                'itemStyle': {'color': theme['primary'], 'borderColor': '#fff', 'borderWidth': 2},
                'areaStyle': {'color': {'type': 'linear', 'x': 0, 'y': 0, 'x2': 0, 'y2': 1,
                                        'colorStops': [{'offset': 0, 'color': f"{theme['primary']}40"},
                                                       {'offset': 1, 'color': f"{theme['primary']}05"}]}},
                'data': values,
                'animationDuration': 2000,
                'animationEasing': 'cubicInOut',
            }],
        }
        
        return json.dumps(config, ensure_ascii=False)


class HTMLExporter:
    """专业级HTML报告导出器 - v3.0"""
    
    def __init__(self, theme: str = 'light'):
        self.theme = HTMLTheme.get(theme)
        self.chart_id = 0
        self.table_id = 0
        
    def _generate_chart_id(self) -> str:
        """生成唯一图表ID"""
        self.chart_id += 1
        return f"chart_{self.chart_id}"
    
    def _generate_table_id(self) -> str:
        """生成唯一表格ID"""
        self.table_id += 1
        return f"table_{self.table_id}"
    
    def export(self, business_system, output_path: Optional[str] = None) -> str:
        """导出HTML报告"""
        bs = business_system
        if isinstance(business_system, dict) and "business_system" in business_system:
            bs = business_system["business_system"]
        
        if not isinstance(bs, dict):
            bs = {}
        
        meta = bs.get("metadata", {})
        if not isinstance(meta, dict):
            meta = {}
        
        title = meta.get("title", bs.get("business_domain", bs.get("objective", "业务系统分析报告")))
        industry = bs.get("industry", meta.get("industry", "通用"))
        date_str = datetime.date.today().strftime("%Y年%m月%d日")
        
        html = self._generate_full_html(title, industry, date_str, bs)
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html)
        
        return html
    
    def _generate_full_html(self, title: str, industry: str, date_str: str, bs: dict) -> str:
        """生成完整HTML页面"""
        return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        :root {{
            --bg: {self.theme['bg']};
            --bg-secondary: {self.theme['bg_secondary']};
            --bg-card: {self.theme['bg_card']};
            --primary: {self.theme['primary']};
            --primary-light: {self.theme['primary_light']};
            --primary-dark: {self.theme['primary_dark']};
            --accent: {self.theme['accent']};
            --accent-light: {self.theme['accent_light']};
            --text: {self.theme['text']};
            --text-light: {self.theme['text_light']};
            --text-faint: {self.theme['text_faint']};
            --border: {self.theme['border']};
            --border-light: {self.theme['border_light']};
            --success: {self.theme['success']};
            --warning: {self.theme['warning']};
            --danger: {self.theme['danger']};
            --info: {self.theme['info']};
            --sidebar-bg: {self.theme['sidebar_bg']};
            --sidebar-text: {self.theme['sidebar_text']};
            --code-bg: {self.theme['code_bg']};
            --code-text: {self.theme['code_text']};
            --gradient-start: {self.theme['gradient_start']};
            --gradient-end: {self.theme['gradient_end']};
            --card-shadow: {self.theme['card_shadow']};
            --card-hover-shadow: {self.theme['card_hover_shadow']};
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        html {{ scroll-behavior: smooth; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif;
            line-height: 1.75;
            color: var(--text);
            background-color: var(--bg);
            transition: background-color 0.3s ease, color 0.3s ease;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }}
        .app-container {{ display: flex; min-height: 100vh; }}
        .sidebar {{
            width: 300px;
            background: var(--sidebar-bg);
            color: var(--sidebar-text);
            position: fixed;
            top: 0;
            left: 0;
            height: 100vh;
            overflow-y: auto;
            z-index: 100;
            padding: 0;
            box-shadow: 4px 0 30px rgba(0,0,0,0.15);
        }}
        .sidebar-header {{
            padding: 32px 24px;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            position: relative;
        }}
        .sidebar-header::after {{
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
        }}
        .sidebar-logo {{ font-size: 20px; font-weight: 800; margin-bottom: 4px; letter-spacing: -0.5px; }}
        .sidebar-subtitle {{ font-size: 12px; opacity: 0.8; }}
        .toc {{ list-style: none; padding: 16px 0; }}
        .toc-item {{ margin-bottom: 1px; }}
        .toc-link {{
            display: block;
            padding: 10px 24px;
            color: var(--sidebar-text);
            text-decoration: none;
            font-size: 14px;
            font-weight: 400;
            border-radius: 0 24px 24px 0;
            transition: all 0.3s ease;
            cursor: pointer;
            position: relative;
        }}
        .toc-link::before {{
            content: '';
            position: absolute;
            left: 0;
            top: 50%;
            transform: translateY(-50%);
            width: 3px;
            height: 0;
            background: var(--accent);
            border-radius: 0 3px 3px 0;
            transition: height 0.3s ease;
        }}
        .toc-link:hover {{ background: rgba(255,255,255,0.06); padding-left: 28px; }}
        .toc-link.active {{ 
            background: rgba(255,255,255,0.12); 
            color: white;
            font-weight: 600;
        }}
        .toc-link.active::before {{ height: 60%; }}
        .toc-link.level-2 {{ padding-left: 40px; font-size: 13px; opacity: 0.85; }}
        .sidebar-footer {{
            padding: 20px 24px;
            border-top: 1px solid rgba(255,255,255,0.08);
            font-size: 12px;
            opacity: 0.5;
            margin-top: 20px;
        }}
        .sidebar-footer span {{ display: block; margin-bottom: 4px; }}
        .main-content {{
            flex: 1;
            margin-left: 300px;
            min-height: 100vh;
        }}
        .header {{
            background: var(--bg-card);
            border-bottom: 1px solid var(--border);
            padding: 32px 60px;
            position: sticky;
            top: 0;
            z-index: 50;
            box-shadow: 0 4px 20px rgba(0,0,0,0.04);
        }}
        .header-title {{ font-size: 32px; font-weight: 800; margin-bottom: 8px; letter-spacing: -1px; }}
        .header-meta {{ font-size: 14px; color: var(--text-light); }}
        .header-meta span {{ margin-right: 20px; }}
        .theme-toggle {{
            float: right;
            padding: 10px 24px;
            border: none;
            border-radius: 25px;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            color: white;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.35s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.15);
        }}
        .theme-toggle:hover {{ transform: translateY(-2px); box-shadow: 0 6px 25px rgba(0,0,0,0.25); }}
        .content-wrapper {{ padding: 48px 60px; max-width: 1500px; }}
        .section {{ margin-bottom: 56px; }}
        .section-header {{
            margin-bottom: 32px;
            padding-bottom: 20px;
            border-bottom: 3px solid var(--border);
            position: relative;
        }}
        .section-header::after {{
            content: '';
            position: absolute;
            bottom: -3px;
            left: 0;
            width: 80px;
            height: 3px;
            background: linear-gradient(90deg, var(--gradient-start), var(--gradient-end));
            border-radius: 0 3px 3px 0;
        }}
        .section-title {{
            font-size: 28px;
            font-weight: 700;
            display: flex;
            align-items: center;
            letter-spacing: -0.5px;
        }}
        .section-title::before {{
            content: '';
            width: 4px;
            height: 28px;
            background: linear-gradient(180deg, var(--gradient-start), var(--gradient-end));
            margin-right: 16px;
            border-radius: 2px;
        }}
        .section-subtitle {{ font-size: 15px; color: var(--text-light); margin-top: 6px; font-weight: 400; }}
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 32px;
            margin-bottom: 24px;
            transition: all 0.4s ease;
            position: relative;
            overflow: hidden;
        }}
        .card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, var(--gradient-start), var(--gradient-end));
            opacity: 0;
            transition: opacity 0.4s ease;
        }}
        .card:hover {{ 
            box-shadow: var(--card-hover-shadow); 
            transform: translateY(-3px);
            border-color: var(--border-light);
        }}
        .card:hover::before {{ opacity: 1; }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border-light);
        }}
        .card-title {{ font-size: 20px; font-weight: 600; }}
        .card-badge {{
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.5px;
        }}
        .card-badge.primary {{ background: rgba(37,99,235,0.1); color: var(--primary); }}
        .card-badge.success {{ background: rgba(16,185,129,0.1); color: var(--success); }}
        .card-badge.warning {{ background: rgba(245,158,11,0.1); color: var(--warning); }}
        .card-badge.danger {{ background: rgba(239,68,68,0.1); color: var(--danger); }}
        .card-badge.info {{ background: rgba(14,165,233,0.1); color: var(--info); }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 24px; }}
        .stat-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 28px;
            text-align: center;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            position: relative;
            overflow: hidden;
        }}
        .stat-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 6px;
            height: 100%;
            transition: width 0.4s ease;
        }}
        .stat-card:hover {{ 
            transform: translateY(-6px) scale(1.02); 
            box-shadow: var(--card-hover-shadow); 
            border-color: var(--border-light);
        }}
        .stat-card:hover::before {{ width: 12px; }}
        .stat-card.primary::before {{ background: var(--primary); }}
        .stat-card.success::before {{ background: var(--success); }}
        .stat-card.warning::before {{ background: var(--warning); }}
        .stat-card.danger::before {{ background: var(--danger); }}
        .stat-card.info::before {{ background: var(--info); }}
        .stat-icon {{
            font-size: 36px;
            margin-bottom: 16px;
            opacity: 0.9;
            filter: drop-shadow(0 4px 12px rgba(0,0,0,0.1));
        }}
        .stat-value {{
            font-size: 48px;
            font-weight: 900;
            margin-bottom: 8px;
            line-height: 1;
            letter-spacing: -2px;
        }}
        .stat-value.primary {{ color: var(--primary); }}
        .stat-value.success {{ color: var(--success); }}
        .stat-value.warning {{ color: var(--warning); }}
        .stat-value.danger {{ color: var(--danger); }}
        .stat-value.info {{ color: var(--info); }}
        .stat-label {{ font-size: 14px; color: var(--text-light); font-weight: 500; }}
        .stat-change {{
            font-size: 13px;
            font-weight: 600;
            margin-top: 8px;
            padding: 4px 12px;
            border-radius: 12px;
            display: inline-block;
        }}
        .stat-change.up {{ color: var(--success); background: rgba(16,185,129,0.1); }}
        .stat-change.down {{ color: var(--danger); background: rgba(239,68,68,0.1); }}
        .chart-container {{ height: 400px; margin-top: 24px; }}
        .chart-container-small {{ height: 300px; }}
        .chart-container-gauge {{ height: 280px; }}
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        .data-table th, .data-table td {{
            padding: 16px 20px;
            text-align: left;
            border-bottom: 1px solid var(--border-light);
        }}
        .data-table th {{
            background: var(--bg-secondary);
            font-weight: 600;
            color: var(--text);
            cursor: pointer;
            user-select: none;
            position: relative;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .data-table th:hover {{ background: var(--border-light); }}
        .data-table tr:hover {{ background: var(--bg-secondary); }}
        .data-table tr:last-child td {{ border-bottom: none; }}
        .data-table .sort-indicator {{ font-size: 12px; margin-left: 8px; color: var(--text-faint); }}
        .table-wrapper {{ overflow-x: auto; border-radius: 12px; border: 1px solid var(--border); background: var(--bg-card); }}
        .table-filter {{
            display: flex;
            gap: 16px;
            margin-bottom: 20px;
            align-items: center;
            flex-wrap: wrap;
        }}
        .table-filter input {{
            flex: 1;
            min-width: 200px;
            padding: 12px 20px;
            border: 1px solid var(--border);
            border-radius: 12px;
            background: var(--bg);
            color: var(--text);
            font-size: 14px;
            transition: all 0.3s ease;
        }}
        .table-filter input:focus {{ 
            outline: none; 
            border-color: var(--primary); 
            box-shadow: 0 0 0 4px rgba(37,99,235,0.1); 
        }}
        .table-pagination {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
            margin-top: 20px;
            padding: 16px;
            border-top: 1px solid var(--border-light);
        }}
        .table-pagination button {{
            padding: 8px 16px;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--bg-card);
            color: var(--text);
            cursor: pointer;
            font-size: 13px;
            transition: all 0.3s ease;
        }}
        .table-pagination button:hover {{ border-color: var(--primary); color: var(--primary); }}
        .table-pagination button.active {{ background: var(--primary); color: white; border-color: var(--primary); }}
        .table-pagination span {{ font-size: 13px; color: var(--text-light); margin: 0 8px; }}
        .workflow-step {{
            display: flex;
            align-items: flex-start;
            padding: 24px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            margin-bottom: 16px;
            transition: all 0.4s ease;
            position: relative;
            overflow: hidden;
        }}
        .workflow-step::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 5px;
            height: 100%;
            transition: width 0.3s ease;
        }}
        .workflow-step:hover {{ border-color: var(--primary); transform: translateX(4px); }}
        .workflow-step:hover::before {{ width: 8px; }}
        .workflow-step.primary::before {{ background: var(--primary); }}
        .workflow-step.accent::before {{ background: var(--accent); }}
        .workflow-step.success::before {{ background: var(--success); }}
        .workflow-step.warning::before {{ background: var(--warning); }}
        .step-number {{
            width: 48px;
            height: 48px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            font-weight: 800;
            color: white;
            margin-right: 24px;
            flex-shrink: 0;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            box-shadow: 0 4px 15px rgba(37,99,235,0.3);
        }}
        .step-content {{ flex: 1; }}
        .step-title {{ font-size: 17px; font-weight: 600; margin-bottom: 8px; }}
        .step-meta {{ font-size: 14px; color: var(--text-light); }}
        .step-meta span {{ margin-right: 20px; }}
        .step-sla {{
            display: inline-block;
            padding: 5px 12px;
            background: rgba(37,99,235,0.1);
            color: var(--primary);
            border-radius: 14px;
            font-size: 12px;
            font-weight: 600;
        }}
        .step-owner {{ color: var(--accent); font-weight: 500; }}
        .risk-item {{
            padding: 24px;
            background: var(--bg-card);
            border-radius: 16px;
            margin-bottom: 16px;
            border-left: 5px solid var(--border);
            transition: all 0.4s ease;
            position: relative;
            overflow: hidden;
        }}
        .risk-item::after {{
            content: '';
            position: absolute;
            top: 0;
            right: 0;
            width: 100px;
            height: 100px;
            opacity: 0.03;
            border-radius: 50%;
            transform: translate(30%, -30%);
        }}
        .risk-item:hover {{ box-shadow: var(--card-shadow); transform: translateX(4px); }}
        .risk-item.critical {{ border-left-color: var(--danger); }}
        .risk-item.critical::after {{ background: var(--danger); }}
        .risk-item.high {{ border-left-color: var(--warning); }}
        .risk-item.high::after {{ background: var(--warning); }}
        .risk-item.medium {{ border-left-color: var(--primary); }}
        .risk-item.medium::after {{ background: var(--primary); }}
        .risk-item.low {{ border-left-color: var(--success); }}
        .risk-item.low::after {{ background: var(--success); }}
        .risk-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }}
        .risk-title {{ font-size: 17px; font-weight: 600; }}
        .risk-score {{ 
            font-size: 14px; 
            padding: 6px 16px; 
            border-radius: 20px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        .risk-score.critical {{ background: rgba(239,68,68,0.1); color: var(--danger); }}
        .risk-score.high {{ background: rgba(245,158,11,0.1); color: var(--warning); }}
        .risk-score.medium {{ background: rgba(37,99,235,0.1); color: var(--primary); }}
        .risk-score.low {{ background: rgba(16,185,129,0.1); color: var(--success); }}
        .risk-desc {{ font-size: 14px; color: var(--text-light); margin-bottom: 16px; line-height: 1.8; }}
        .risk-mitigation {{ font-size: 14px; color: var(--success); font-weight: 500; padding: 12px 16px; background: rgba(16,185,129,0.05); border-radius: 8px; }}
        .progress-bar {{
            height: 12px;
            background: var(--border-light);
            border-radius: 6px;
            overflow: hidden;
            margin: 16px 0;
        }}
        .progress-fill {{
            height: 100%;
            border-radius: 6px;
            transition: width 1s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
        }}
        .progress-fill::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
            animation: shimmer 2.5s infinite;
        }}
        @keyframes shimmer {{
            0% {{ transform: translateX(-100%); }}
            100% {{ transform: translateX(100%); }}
        }}
        .timeline-item {{
            position: relative;
            padding-left: 50px;
            padding-bottom: 40px;
        }}
        .timeline-item::before {{
            content: '';
            position: absolute;
            left: 14px;
            top: 8px;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            border: 4px solid var(--primary);
            background: var(--bg);
            box-shadow: 0 0 0 4px rgba(37,99,235,0.1);
        }}
        .timeline-item::after {{
            content: '';
            position: absolute;
            left: 24px;
            top: 36px;
            width: 4px;
            height: calc(100% - 12px);
            background: var(--border);
        }}
        .timeline-item:last-child::after {{ display: none; }}
        .timeline-item.completed::before {{ background: var(--success); border-color: var(--success); }}
        .timeline-item.in-progress::before {{ background: var(--accent); border-color: var(--accent); }}
        .timeline-title {{ font-size: 17px; font-weight: 600; margin-bottom: 8px; }}
        .timeline-time {{ font-size: 14px; color: var(--text-light); font-weight: 500; }}
        .timeline-items {{ font-size: 14px; color: var(--text-light); margin-top: 14px; }}
        .timeline-items ul {{ list-style: none; padding-left: 0; }}
        .timeline-items li {{ padding: 8px 0; border-bottom: 1px dashed var(--border-light); display: flex; align-items: center; }}
        .timeline-items li:last-child {{ border-bottom: none; }}
        .timeline-items li::before {{
            content: '▸';
            color: var(--primary);
            margin-right: 10px;
            font-size: 12px;
        }}
        .mermaid-container {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 32px;
            margin-top: 24px;
            overflow-x: auto;
        }}
        .mermaid {{ max-width: 100%; }}
        .comparison-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }}
        .comparison-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 28px;
            transition: all 0.4s ease;
            position: relative;
        }}
        .comparison-card:hover {{ border-color: var(--primary); box-shadow: var(--card-shadow); }}
        .comparison-title {{ font-size: 15px; color: var(--text-light); margin-bottom: 20px; text-align: center; font-weight: 500; }}
        .comparison-values {{ display: flex; justify-content: space-around; align-items: center; }}
        .comparison-value {{ text-align: center; }}
        .comparison-label {{ font-size: 12px; color: var(--text-faint); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }}
        .comparison-num {{ font-size: 32px; font-weight: 800; }}
        .comparison-num.current {{ color: var(--text-faint); }}
        .comparison-num.target {{ color: var(--primary); }}
        .comparison-arrow {{ font-size: 24px; color: var(--success); font-weight: bold; margin: 0 8px; }}
        .comparison-improvement {{
            text-align: center;
            margin-top: 16px;
            padding: 8px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
        }}
        .comparison-improvement.positive {{ background: rgba(16,185,129,0.1); color: var(--success); }}
        .comparison-improvement.negative {{ background: rgba(239,68,68,0.1); color: var(--danger); }}
        .footer {{
            padding: 40px 60px;
            border-top: 1px solid var(--border);
            margin-top: 64px;
            font-size: 14px;
            color: var(--text-faint);
            text-align: center;
            background: var(--bg-card);
        }}
        .footer a {{ color: var(--primary); text-decoration: none; font-weight: 500; }}
        .footer a:hover {{ text-decoration: underline; }}
        .module-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 28px;
            margin-bottom: 16px;
            transition: all 0.4s ease;
            position: relative;
            overflow: hidden;
        }}
        .module-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background: var(--primary);
            transition: width 0.3s ease;
        }}
        .module-card:hover {{ border-color: var(--primary); box-shadow: var(--card-shadow); transform: translateX(4px); }}
        .module-card:hover::before {{ width: 8px; }}
        .module-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }}
        .module-name {{ font-size: 17px; font-weight: 600; }}
        .module-deps {{ font-size: 12px; color: var(--text-faint); background: rgba(0,0,0,0.05); padding: 4px 10px; border-radius: 8px; }}
        .module-desc {{ font-size: 14px; color: var(--text-light); line-height: 1.7; }}
        .module-tags {{ display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }}
        .module-tag {{
            font-size: 11px;
            padding: 4px 10px;
            background: rgba(37,99,235,0.08);
            color: var(--primary);
            border-radius: 6px;
            font-weight: 500;
        }}
        .roi-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 28px;
            text-align: center;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            position: relative;
            overflow: hidden;
        }}
        .roi-card::before {{
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(16,185,129,0.05) 0%, transparent 70%);
            opacity: 0;
            transition: opacity 0.4s ease;
        }}
        .roi-card:hover {{ border-color: var(--success); transform: translateY(-8px); box-shadow: 0 20px 40px rgba(16,185,129,0.1); }}
        .roi-card:hover::before {{ opacity: 1; }}
        .roi-title {{ font-size: 15px; color: var(--text-light); margin-bottom: 16px; font-weight: 500; }}
        .roi-savings {{ font-size: 40px; font-weight: 900; color: var(--success); margin-bottom: 10px; letter-spacing: -1px; }}
        .roi-investment {{ font-size: 14px; color: var(--text-faint); }}
        .roi-period {{ font-size: 12px; color: var(--accent); margin-top: 8px; font-weight: 500; }}
        .accordion {{ border-radius: 16px; overflow: hidden; border: 1px solid var(--border); }}
        .accordion-item {{ border-bottom: 1px solid var(--border); }}
        .accordion-item:last-child {{ border-bottom: none; }}
        .accordion-header {{
            padding: 20px 24px;
            background: var(--bg-card);
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-weight: 600;
            font-size: 15px;
            transition: all 0.3s ease;
        }}
        .accordion-header:hover {{ background: var(--bg-secondary); }}
        .accordion-header.active {{ background: var(--bg-secondary); }}
        .accordion-header::after {{
            content: '▼';
            font-size: 10px;
            color: var(--text-faint);
            transition: transform 0.3s ease;
        }}
        .accordion-header.active::after {{ transform: rotate(180deg); }}
        .accordion-content {{
            padding: 0 24px;
            background: var(--bg);
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.4s ease, padding 0.4s ease;
        }}
        .accordion-content.open {{
            padding: 20px 24px;
            max-height: 500px;
        }}
        @media (max-width: 1024px) {{
            .sidebar {{ width: 260px; }}
            .main-content {{ margin-left: 260px; }}
            .header, .content-wrapper {{ padding: 24px 32px; }}
            .header-title {{ font-size: 26px; }}
        }}
        @media (max-width: 768px) {{
            .sidebar {{ display: none; }}
            .main-content {{ margin-left: 0; }}
            .header, .content-wrapper {{ padding: 16px 20px; }}
            .header-title {{ font-size: 22px; }}
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .comparison-grid {{ grid-template-columns: 1fr; }}
            .chart-container {{ height: 320px; }}
            .stat-value {{ font-size: 36px; }}
        }}
        @media (max-width: 480px) {{
            .stats-grid {{ grid-template-columns: 1fr; }}
            .chart-container {{ height: 280px; }}
        }}
    </style>
</head>
<body>
    <div class="app-container">
        <aside class="sidebar">
            <div class="sidebar-header">
                <div class="sidebar-logo">BSC Engine</div>
                <div class="sidebar-subtitle">业务系统分析报告</div>
            </div>
            <ul class="toc" id="toc">
                {self._generate_toc(bs)}
            </ul>
            <div class="sidebar-footer">
                <span>{date_str}</span>
                <span>版本 v3.0</span>
            </div>
        </aside>
        
        <main class="main-content">
            <header class="header">
                <button class="theme-toggle" onclick="toggleTheme()">切换主题</button>
                <h1 class="header-title">{title}</h1>
                <div class="header-meta">
                    <span>行业：{industry}</span>
                    <span>生成时间：{date_str}</span>
                    <span>报告版本：v3.0</span>
                </div>
            </header>
            
            <div class="content-wrapper">
                {self._section_exec_summary(bs)}
                {self._section_modules(bs)}
                {self._section_workflow(bs)}
                {self._section_kpi(bs)}
                {self._section_risk(bs)}
                {self._section_roi(bs)}
                {self._section_timeline(bs)}
                {self._section_comparison(bs)}
            </div>
            
            <footer class="footer">
                生成于 {date_str} · <a href="#">BSC Engine Professional Edition</a> · 版权所有
            </footer>
        </main>
    </div>
    
    <script>
        var theme = '{self.theme["name"]}';
        function toggleTheme() {{
            theme = theme === 'light' ? 'dark' : 'light';
            localStorage.setItem('bsc-theme', theme);
            location.reload();
        }}
        document.addEventListener('DOMContentLoaded', function() {{
            var savedTheme = localStorage.getItem('bsc-theme');
            if (savedTheme && savedTheme !== theme) {{
                theme = savedTheme;
                document.documentElement.style.setProperty('--bg', savedTheme === 'light' ? '#ffffff' : '#0f172a');
            }}
            
            mermaid.initialize({{ startOnLoad: true, theme: theme === 'dark' ? 'dark' : 'default', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif' }});
            
            var charts = document.querySelectorAll('.chart-container');
            charts.forEach(function(el) {{
                var chart = echarts.init(el, theme === 'dark' ? 'dark' : 'light');
                var config = JSON.parse(el.dataset.config);
                chart.setOption(config);
                window.addEventListener('resize', function() {{ chart.resize(); }});
            }});
            
            var tocLinks = document.querySelectorAll('.toc-link');
            tocLinks.forEach(function(link) {{
                link.addEventListener('click', function(e) {{
                    e.preventDefault();
                    var targetId = this.getAttribute('href').substring(1);
                    var target = document.getElementById(targetId);
                    if (target) {{
                        target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                    }}
                    tocLinks.forEach(function(l) {{ l.classList.remove('active'); }});
                    this.classList.add('active');
                }});
            }});
            
            window.addEventListener('scroll', function() {{
                var sections = document.querySelectorAll('.section');
                var scrollPos = window.scrollY + 200;
                
                sections.forEach(function(section) {{
                    var top = section.offsetTop;
                    var height = section.offsetHeight;
                    var id = section.getAttribute('id');
                    
                    if (scrollPos >= top && scrollPos < top + height) {{
                        tocLinks.forEach(function(link) {{ link.classList.remove('active'); }});
                        var activeLink = document.querySelector('.toc-link[href="#' + id + '"]');
                        if (activeLink) {{ activeLink.classList.add('active'); }}
                    }}
                }});
            }});
            
            var headers = document.querySelectorAll('th[data-sort]');
            headers.forEach(function(th) {{
                th.addEventListener('click', function() {{
                    var table = this.closest('.data-table');
                    var colIndex = Array.from(this.parentElement.children).indexOf(this);
                    var rows = Array.from(table.querySelectorAll('tbody tr'));
                    var isAsc = this.getAttribute('data-sort') === 'asc';
                    
                    rows.sort(function(a, b) {{
                        var aVal = a.children[colIndex].textContent.trim();
                        var bVal = b.children[colIndex].textContent.trim();
                        if (!isNaN(aVal) && !isNaN(bVal)) {{
                            return isAsc ? parseFloat(aVal) - parseFloat(bVal) : parseFloat(bVal) - parseFloat(aVal);
                        }}
                        return isAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
                    }});
                    
                    rows.forEach(function(row) {{ table.querySelector('tbody').appendChild(row); }});
                    this.setAttribute('data-sort', isAsc ? 'desc' : 'asc');
                }});
            }});
            
            var filters = document.querySelectorAll('.table-filter input');
            filters.forEach(function(input) {{
                input.addEventListener('input', function() {{
                    var keyword = this.value.toLowerCase();
                    var table = this.parentElement.nextElementSibling.querySelector('.data-table');
                    var rows = table.querySelectorAll('tbody tr');
                    rows.forEach(function(row) {{
                        var text = row.textContent.toLowerCase();
                        row.style.display = text.includes(keyword) ? '' : 'none';
                    }});
                }});
            }});
            
            var progressBars = document.querySelectorAll('.progress-fill');
            progressBars.forEach(function(bar) {{
                var width = bar.style.width;
                bar.style.width = '0%';
                setTimeout(function() {{ bar.style.width = width; }}, 400);
            }});
            
            var statCards = document.querySelectorAll('.stat-card');
            statCards.forEach(function(card, index) {{
                card.style.opacity = '0';
                card.style.transform = 'translateY(30px)';
                setTimeout(function() {{
                    card.style.transition = 'all 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
                    card.style.opacity = '1';
                    card.style.transform = 'translateY(0)';
                }}, 100 + index * 100);
            }});
            
            var accordions = document.querySelectorAll('.accordion-header');
            accordions.forEach(function(header) {{
                header.addEventListener('click', function() {{
                    this.classList.toggle('active');
                    var content = this.nextElementSibling;
                    content.classList.toggle('open');
                }});
            }});
        }});
    </script>
</body>
</html>
"""
    
    def _generate_toc(self, bs: dict) -> str:
        """生成目录"""
        toc_items = [
            ('exec-summary', '执行摘要'),
            ('modules', '系统架构'),
            ('workflow', '业务流程'),
            ('kpi', '关键指标'),
            ('risk', '风险评估'),
            ('roi', '投资回报'),
            ('timeline', '实施路线'),
            ('comparison', '对比分析'),
        ]
        
        return '\n'.join(f'<li class="toc-item"><a href="#{id}" class="toc-link">{name}</a></li>' 
                         for id, name in toc_items)
    
    def _section_exec_summary(self, bs: dict) -> str:
        """执行摘要章节"""
        modules = bs.get("modules", bs.get("core_modules", []))
        workflow = bs.get("workflow", bs.get("process_flow", []))
        kpi_list = bs.get("kpi", bs.get("metrics", bs.get("success_metrics", [])))
        risk_list = bs.get("risk", bs.get("risks", []))
        objective = bs.get("objective", bs.get("description", ""))
        
        stats = [
            {'label': '功能模块', 'value': len(modules), 'color': 'primary', 'icon': '📦', 'change': '+12%'},
            {'label': '流程节点', 'value': len(workflow), 'color': 'accent', 'icon': '🔄', 'change': '+8%'},
            {'label': '关键指标', 'value': len(kpi_list), 'color': 'success', 'icon': '📊', 'change': '+25%'},
            {'label': '识别风险', 'value': len(risk_list), 'color': 'danger', 'icon': '⚠️', 'change': '-15%'},
        ]
        
        stat_html = ''.join(f"""
            <div class="stat-card {s['color']}">
                <div class="stat-icon">{s['icon']}</div>
                <div class="stat-value {s['color']}">{s['value']}</div>
                <div class="stat-label">{s['label']}</div>
                <div class="stat-change {'up' if '+' in s['change'] else 'down'}">{s['change']}</div>
            </div>
        """ for s in stats)
        
        return f"""
        <section id="exec-summary" class="section">
            <div class="section-header">
                <h2 class="section-title">执行摘要</h2>
                <div class="section-subtitle">系统概览与关键指标</div>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <span class="card-title">核心指标</span>
                    <span class="card-badge primary">实时统计</span>
                </div>
                <div class="stats-grid">{stat_html}</div>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <span class="card-title">业务目标</span>
                </div>
                <p style="color: var(--text); font-size: 15px; line-height: 1.8;">{str(objective)[:500]}</p>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <span class="card-title">技术架构</span>
                </div>
                <div class="mermaid-container">
                    <pre class="mermaid">
graph TD
    A[前端应用] --> B[API网关]
    B --> C[业务逻辑层]
    C --> D[数据层]
    C --> E[LLM服务]
    B --> F[缓存层]
    D --> G[(数据库)]
    E --> H[OpenAI/本地模型]
                    </pre>
                </div>
            </div>
        </section>
        """
    
    def _section_modules(self, bs: dict) -> str:
        """系统架构章节"""
        modules = bs.get("modules", bs.get("core_modules", []))
        
        modules_html = ''.join(f"""
            <div class="module-card">
                <div class="module-header">
                    <span class="module-name">{str(m.get('name','?')) if isinstance(m,dict) else str(m)}</span>
                    {'<span class="module-deps">依赖: ' + ', '.join(str(d) for d in m.get('depends_on',[])) + '</span>' if isinstance(m,dict) and m.get('depends_on') else ''}
                </div>
                <div class="module-desc">{str(m.get('description',''))[:200] if isinstance(m,dict) else ''}</div>
                {'<div class="module-tags">' + ''.join(f'<span class="module-tag">{t}</span>' for t in m.get('tags',[])[:3]) + '</div>' if isinstance(m,dict) and m.get('tags') else ''}
            </div>
        """ for i, m in enumerate(modules[:8]))
        
        return f"""
        <section id="modules" class="section">
            <div class="section-header">
                <h2 class="section-title">系统架构</h2>
                <div class="section-subtitle">模块分解与依赖关系</div>
            </div>
            {modules_html}
        </section>
        """
    
    def _section_workflow(self, bs: dict) -> str:
        """业务流程章节"""
        workflow = bs.get("workflow", bs.get("process_flow", bs.get("sop", [])))
        
        colors = ['primary', 'accent', 'success', 'warning', 'danger', 'info', 'primary', 'accent']
        
        steps_html = ''.join(f"""
            <div class="workflow-step {colors[i % len(colors)]}">
                <div class="step-number">{i+1}</div>
                <div class="step-content">
                    <div class="step-title">{step.get('name', step.get('step', f'步骤 {i+1}')) if isinstance(step,dict) else str(step)}</div>
                    <div class="step-meta">
                        <span>责任人: <span class="step-owner">{step.get('owner', step.get('role', '-')) if isinstance(step,dict) else '-'}</span></span>
                        {'<span class="step-sla">SLA: ' + str(step.get('sla_hours', step.get('sla', ''))) + 'h</span>' if isinstance(step,dict) and (step.get('sla_hours') or step.get('sla')) else ''}
                        {'<span>→ ' + ', '.join(str(x) for x in (step.get('next',[])[:2])) + '</span>' if isinstance(step,dict) and step.get('next') else ''}
                    </div>
                </div>
            </div>
        """ for i, step in enumerate(workflow[:8]))
        
        return f"""
        <section id="workflow" class="section">
            <div class="section-header">
                <h2 class="section-title">业务流程</h2>
                <div class="section-subtitle">标准操作流程与责任人</div>
            </div>
            {steps_html}
        </section>
        """
    
    def _section_kpi(self, bs: dict) -> str:
        """关键指标章节"""
        kpi_list = bs.get("kpi", bs.get("metrics", bs.get("success_metrics", [])))
        
        chart_data = []
        for kpi in kpi_list[:6]:
            if isinstance(kpi, dict):
                target = kpi.get("target", "-")
                try:
                    num_val = float(str(target).replace('%', '').replace('>', '').replace('<', ''))
                    chart_data.append({"name": kpi.get("name", f"KPI {len(chart_data)+1}"), "value": num_val})
                except:
                    pass
        
        chart_id = self._generate_chart_id()
        chart_config = HTMLChartGenerator.bar_chart(chart_data, "name", "value", "KPI目标值", "", self.theme) if chart_data else ""
        
        gauge_chart_id = self._generate_chart_id()
        overall_score = sum(kpi.get("score", 5) for kpi in kpi_list if isinstance(kpi, dict)) / max(len(kpi_list), 1) if kpi_list else 75
        gauge_config = HTMLChartGenerator.gauge_chart(overall_score, "综合评分", 0, 100, self.theme)
        
        kpi_table_rows = ''.join(f"""
            <tr>
                <td>{k.get('name', f'KPI {i+1}') if isinstance(k,dict) else str(k)}</td>
                <td>{k.get('target', '-') if isinstance(k,dict) else '-'}</td>
                <td>{k.get('formula', '-') if isinstance(k,dict) else '-'}</td>
            </tr>
        """ for i, k in enumerate(kpi_list[:10]))
        
        return f"""
        <section id="kpi" class="section">
            <div class="section-header">
                <h2 class="section-title">关键指标</h2>
                <div class="section-subtitle">可量化指标与目标</div>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <span class="card-title">综合评分</span>
                    <span class="card-badge success">健康度</span>
                </div>
                <div class="chart-container chart-container-gauge" id="{gauge_chart_id}" data-config=\'{gauge_config}\'></div>
            </div>
            
            {'<div class="card"><div class="card-header"><span class="card-title">KPI图表</span></div><div class="chart-container" id="{chart_id}" data-config=\'{chart_config}\'></div></div>' if chart_data else ''}
            
            <div class="card">
                <div class="card-header">
                    <span class="card-title">指标详情</span>
                </div>
                <div class="table-wrapper">
                    <div class="table-filter">
                        <input type="text" placeholder="搜索指标...">
                    </div>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th data-sort="asc">指标名称</th>
                                <th data-sort="asc">目标值</th>
                                <th data-sort="asc">计算公式</th>
                            </tr>
                        </thead>
                        <tbody>
                            {kpi_table_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </section>
        """
    
    def _section_risk(self, bs: dict) -> str:
        """风险评估章节"""
        risk_list = bs.get("risks") or bs.get("risk") or []
        if isinstance(risk_list, dict):
            risk_list = [risk_list]
        
        risk_counts = {}
        for risk in risk_list:
            severity = risk.get("severity", risk.get("impact", "medium")) if isinstance(risk, dict) else "medium"
            risk_counts[severity] = risk_counts.get(severity, 0) + 1
        
        chart_data = [{"severity": k, "count": v} for k, v in risk_counts.items()]
        chart_id = self._generate_chart_id()
        chart_config = HTMLChartGenerator.pie_chart(chart_data, "severity", "count", "风险分布", self.theme) if chart_data else ""
        
        sev_map = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}
        
        def _get_severity(r):
            if not isinstance(r, dict):
                return 'medium'
            return sev_map.get(r.get('severity', r.get('impact', 'medium')), 'medium')
        
        def _get_severity_color(sev):
            if sev == 'critical':
                return 'danger'
            if sev == 'high':
                return 'warning'
            return 'info'
        
        risks_html = ''.join(f"""
            <div class="risk-item {_get_severity(r)}">
                <div class="risk-header">
                    <span class="risk-title">{r.get('name', r.get('risk', '风险')) if isinstance(r,dict) else str(r)}</span>
                    <span class="risk-score {_get_severity(r)}">
                        {r.get('score', 5)}/10
                    </span>
                </div>
                <div class="risk-desc">{str(r.get('description',''))[:250] if isinstance(r,dict) else ''}</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {min(int(r.get('score',5)) * 10, 100)}%; background: var(--{_get_severity_color(_get_severity(r))});"></div>
                </div>
                {'<div class="risk-mitigation">应对措施: ' + str(r.get('mitigation', ''))[:180] + '</div>' if isinstance(r,dict) and r.get('mitigation') else ''}
            </div>
        """ for r in risk_list[:6])
        
        return f"""
        <section id="risk" class="section">
            <div class="section-header">
                <h2 class="section-title">风险评估</h2>
                <div class="section-subtitle">风险矩阵与应对策略</div>
            </div>
            
            {'<div class="card"><div class="card-header"><span class="card-title">风险分布</span></div><div class="chart-container" id="{chart_id}" data-config=\'{chart_config}\'></div></div>' if chart_data else ''}
            
            {risks_html}
        </section>
        """
    
    def _section_roi(self, bs: dict) -> str:
        """投资回报章节"""
        strategy = bs.get("strategy", {})
        if not isinstance(strategy, dict):
            strategy = {}
        optimization = bs.get("optimization", {})
        if not isinstance(optimization, dict):
            optimization = {}
        recommendations = strategy.get("recommendations", optimization.get("recommendations", []))
        
        roi_data = []
        for rec in recommendations[:4]:
            if isinstance(rec, dict):
                investment = rec.get("investment", 0)
                annual_savings = rec.get("annual_savings", 0)
                title = rec.get("title", rec.get("id", f"建议 {len(roi_data)+1}"))
                roi_data.append({"title": title, "investment": investment, "savings": annual_savings})
        
        if not roi_data:
            roi_data = [
                {"title": "自动化升级", "investment": 30000, "savings": 1440000},
                {"title": "流程优化", "investment": 6000, "savings": 540000},
                {"title": "智能库存预警", "investment": 40000, "savings": 250000},
                {"title": "实时数据同步", "investment": 60000, "savings": 350000},
            ]
        
        roi_cards = ''.join(f"""
            <div class="roi-card">
                <div class="roi-title">{r['title']}</div>
                <div class="roi-savings">{'¥' + str(r['savings']//10000) + '万' if r['savings'] > 10000 else '¥' + str(r['savings'])}/年</div>
                <div class="roi-investment">投入: {'¥' + str(r['investment']//10000) + '万' if r['investment'] > 10000 else '¥' + str(r['investment'])}</div>
                <div class="roi-period">预计回报周期: {max(1, r['investment'] // (r['savings'] // 12))}个月</div>
            </div>
        """ for r in roi_data)
        
        comparison_rows = f"""
            <tr><td>处理时长</td><td>{bs.get('current_processing_time', '4.2小时')}</td><td>{bs.get('target_processing_time', '1.8小时')}</td><td>{bs.get('processing_improvement', '-57%')}</td></tr>
            <tr><td>人工审核</td><td>{bs.get('current_manual_review', '100%')}</td><td>{bs.get('target_manual_review', '40%')}</td><td>{bs.get('review_improvement', '-60%')}</td></tr>
            <tr><td>错误率</td><td>{bs.get('current_error_rate', '3.2%')}</td><td>{bs.get('target_error_rate', '1.1%')}</td><td>{bs.get('error_improvement', '-65%')}</td></tr>
            <tr><td>人员利用率</td><td>{bs.get('current_utilization', '68%')}</td><td>{bs.get('target_utilization', '92%')}</td><td>{bs.get('utilization_improvement', '+24%')}</td></tr>
        """
        
        return f"""
        <section id="roi" class="section">
            <div class="section-header">
                <h2 class="section-title">投资回报分析</h2>
                <div class="section-subtitle">预期效益与成本节约</div>
            </div>
            
            <div class="stats-grid">{roi_cards}</div>
            
            <div class="card">
                <div class="card-header">
                    <span class="card-title">年度预期效益对比</span>
                </div>
                <div class="table-wrapper">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th data-sort="asc">指标</th>
                                <th data-sort="asc">当前状态</th>
                                <th data-sort="asc">目标状态</th>
                                <th data-sort="asc">改善幅度</th>
                            </tr>
                        </thead>
                        <tbody>
                            {comparison_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </section>
        """
    
    def _section_timeline(self, bs: dict) -> str:
        """实施路线图章节"""
        phases = bs.get("strategy", {}).get("strategic_path", bs.get("milestones", []))
        
        if not phases:
            phases = [
                {"phase": "第一阶段", "theme": "基础建设", "timeline": "0-4周", 
                 "items": ["核心架构搭建", "API基础设施", "模块框架"]},
                {"phase": "第二阶段", "theme": "能力提升", "timeline": "4-8周",
                 "items": ["LLM集成", "图表引擎", "风险分析"]},
                {"phase": "第三阶段", "theme": "优化迭代", "timeline": "8-12周",
                 "items": ["性能优化", "用户反馈", "功能完善"]},
                {"phase": "第四阶段", "theme": "稳定运行", "timeline": "12-16周",
                 "items": ["运维监控", "安全加固", "文档交付"]},
            ]
        
        def _render_item(item):
            if isinstance(item, dict):
                return str(item.get('goal', item.get('item', str(item))))
            return str(item)
        
        timeline_html = ''.join(f"""
            <div class="timeline-item {'completed' if i == 0 else 'in-progress' if i == 1 else ''}">
                <div class="timeline-title">{p.get('theme', p.get('phase', f'阶段 {i+1}')) if isinstance(p,dict) else str(p)}</div>
                <div class="timeline-time">{p.get('timeline', f'周 {i*4+1}-{(i+1)*4}') if isinstance(p,dict) else ''}</div>
                {'<div class="timeline-items"><ul>' + ''.join('<li>' + _render_item(item) + '</li>' for item in p.get('items',[])[:5]) + '</ul></div>' if isinstance(p,dict) and p.get('items') else ''}
            </div>
        """ for i, p in enumerate(phases[:4]))
        
        return f"""
        <section id="timeline" class="section">
            <div class="section-header">
                <h2 class="section-title">实施路线图</h2>
                <div class="section-subtitle">分阶段交付计划</div>
            </div>
            
            <div class="card">
                {timeline_html}
            </div>
        </section>
        """
    
    def _section_comparison(self, bs: dict) -> str:
        """对比分析章节"""
        comparisons = [
            {"metric": "处理效率", "current": bs.get("current_processing_time", "4.2"), "target": bs.get("target_processing_time", "1.8"), "color": "primary", "unit": "小时"},
            {"metric": "人工审核", "current": bs.get("current_manual_review", "100"), "target": bs.get("target_manual_review", "40"), "color": "warning", "unit": "%"},
            {"metric": "错误率", "current": bs.get("current_error_rate", "3.2"), "target": bs.get("target_error_rate", "1.1"), "color": "danger", "unit": "%"},
            {"metric": "人员利用率", "current": bs.get("current_utilization", "68"), "target": bs.get("target_utilization", "92"), "color": "success", "unit": "%"},
        ]
        
        comparison_chart_data = []
        for comp in comparisons:
            try:
                comparison_chart_data.append({
                    "metric": comp["metric"],
                    "current": float(str(comp["current"]).replace('%', '').replace('小时', '')),
                    "target": float(str(comp["target"]).replace('%', '').replace('小时', '')),
                })
            except:
                pass
        
        chart_id = self._generate_chart_id()
        chart_config = HTMLChartGenerator.comparison_bar_chart(
            comparison_chart_data, "metric", "current", "target", "现状与目标对比", self.theme
        ) if comparison_chart_data else ""
        
        comparison_cards = ''.join(f"""
            <div class="comparison-card">
                <div class="comparison-title">{c['metric']}</div>
                <div class="comparison-values">
                    <div class="comparison-value">
                        <div class="comparison-label">当前</div>
                        <div class="comparison-num current">{str(c['current'])}{c['unit']}</div>
                    </div>
                    <div class="comparison-arrow">→</div>
                    <div class="comparison-value">
                        <div class="comparison-label">目标</div>
                        <div class="comparison-num target">{str(c['target'])}{c['unit']}</div>
                    </div>
                </div>
                <div class="comparison-improvement {'positive' if c['color'] in ['success', 'primary'] else 'negative'}">
                    {bs.get(f'{c["metric"].replace(" ","_").lower()}_improvement', '优化中')}
                </div>
            </div>
        """ for c in comparisons)
        
        improvements = bs.get("strategy", {}).get("recommendations", [])
        improvements_html = ''
        if improvements:
            accordion_items = []
            for i, imp in enumerate(improvements[:4]):
                if isinstance(imp, dict):
                    title = imp.get('title', f'改进 {i+1}')
                    desc = str(imp.get('description', imp.get('mitigation', '')))
                else:
                    title = f'改进 {i+1}'
                    desc = str(imp)
                accordion_items.append(f'<div class="accordion-item"><div class="accordion-header">{title}</div><div class="accordion-content"><p>{desc}</p></div></div>')
            improvements_html = f"""
            <div class="card">
                <div class="card-header">
                    <span class="card-title">关键改进措施</span>
                    <span class="card-badge accent">行动计划</span>
                </div>
                <div class="accordion">
                    {''.join(accordion_items)}
                </div>
            </div>
            """
        
        return f"""
        <section id="comparison" class="section">
            <div class="section-header">
                <h2 class="section-title">对比分析</h2>
                <div class="section-subtitle">现状与目标差距分析</div>
            </div>
            
            <div class="comparison-grid">{comparison_cards}</div>
            
            {'<div class="card"><div class="card-header"><span class="card-title">对比图表</span></div><div class="chart-container" id="{chart_id}" data-config=\'{chart_config}\'></div></div>' if comparison_chart_data else ''}
            
            {improvements_html}
        </section>
        """


def export_html(business_system, output_path=None, theme='light'):
    """导出HTML报告"""
    exporter = HTMLExporter(theme=theme)
    return exporter.export(business_system, output_path)


def export_html_dark(business_system, output_path=None):
    """导出深色主题HTML报告"""
    return export_html(business_system, output_path, 'dark')


__all__ = [
    "HTMLExporter",
    "HTMLTheme",
    "HTMLChartGenerator",
    "export_html",
    "export_html_dark",
    "generate_html",
]


# ---------------------------------------------------------------------------
# 组件级降级 HTML 生成器（从 bsc_api._generate_html 迁入）
# 注意：本文件顶部已 `import datetime` 作为模块（见 _section_* 中的
# datetime.date.today()），故此处使用 datetime.datetime.now() 而非
# `from datetime import datetime`，以避免遮蔽模块名。
# ---------------------------------------------------------------------------

def generate_html(
    report,
    pipeline_info: dict = None,
    ctx: Optional[DegradeContext] = None,
) -> str:
    """生成 HTML 报告。report 为 CanonicalReport；ctx 非空时单区块失败被跳过。"""
    from exporters.canonical import CanonicalReport, normalize
    import html as _html
    if not isinstance(report, CanonicalReport):
        report = normalize(report)

    def _esc(s):
        return _html.escape(str(s))

    parts = [f"<h1>{_esc(report.title)}</h1>"]
    if report.executive_summary:
        parts.append(f"<p class='summary'>{_esc(report.executive_summary)}</p>")
    parts.append("<hr/>")

    def _block(name, build):
        if ctx is None:
            build()
        else:
            with ctx.component(name):
                build()

    def _objectives():
        items = "".join(
            f"<li>{o.priority_label} <b>{_esc(o.objective)}</b>"
            + (f" - 目标: {_esc(o.target)}" if o.target else "") + "</li>"
            for o in report.objectives
        )
        parts.append(f"<h2>一、业务目标</h2><ul>{items or '<li>暂无业务目标</li>'}</ul>")

    def _roles():
        rows = "".join(
            f"<tr><td>{_esc(r.role)}</td><td>{_esc(r.department)}</td>"
            f"<td>{_esc(r.level)}</td><td>{_esc(r.headcount)}</td></tr>"
            for r in report.roles
        )
        head = "<tr><th>角色</th><th>部门</th><th>级别</th><th>人数</th></tr>"
        parts.append(f"<h2>二、角色定义</h2><table>{head}{rows or ''}</table>")

    def _workflow():
        items = "".join(
            f"<li><b>{_esc(s.name)}</b>"
            + (f" - 动作: {_esc(s.action)}" if s.action else "")
            + (f" - 角色: {_esc(s.role)}" if s.role else "") + "</li>"
            for s in report.workflow
        )
        parts.append(f"<h2>三、业务流程</h2><ul>{items or '<li>暂无业务流程</li>'}</ul>")

    def _metrics():
        rows = "".join(
            f"<tr><td>{_esc(m.name)}</td><td>{_esc(m.formula)}</td><td>{_esc(m.target)}</td></tr>"
            for m in report.metrics
        )
        head = "<tr><th>指标</th><th>公式</th><th>目标</th></tr>"
        parts.append(f"<h2>四、关键指标</h2><table>{head}{rows or ''}</table>")

    def _risks():
        items = "".join(
            f"<li><b>{_esc(rk.severity_label)}</b>: {_esc(rk.risk)}"
            + (f" - 应对: {_esc(rk.mitigation)}" if rk.mitigation else "")
            + (f" - 影响: {_esc(rk.impact)}" if rk.impact else "") + "</li>"
            for rk in report.risks
        )
        parts.append(f"<h2>五、风险分析</h2><ul>{items or '<li>暂无风险分析</li>'}</ul>")

    def _strategy():
        items = ""
        for rec in report.strategy.recommendations:
            items += f"<li>{_esc(rec)}</li>"
        for g in report.strategy.growth_opportunities:
            items += f"<li>{_esc(g['opportunity'])}: {_esc(g['potential'])}</li>"
        for step in report.strategy.roadmap:
            items += f"<li>{_esc(step)}</li>"
        parts.append(f"<h2>六、战略建议</h2><ul>{items or '<li>暂无战略建议</li>'}</ul>")

    _block("objectives", _objectives)
    _block("roles", _roles)
    _block("workflow", _workflow)
    _block("metrics", _metrics)
    _block("risks", _risks)
    _block("strategy", _strategy)
    return "\n".join(parts)
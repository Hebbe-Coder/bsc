"""
PRD Document Model - PRD文档模型

定义PRD文档的结构化表示，支持：
1. Markdown ↔ SectionTree 双向转换
2. 实时编辑（增删改Section）
3. 实时预览（SectionTree → HTML）
4. 多格式导出（PDF/PPT/Word）的统一数据基础
"""
from __future__ import annotations
import re
import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, model_validator


class PRDSection(BaseModel):
    """PRD章节模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="章节唯一标识")
    title: str = Field(..., description="章节标题")
    content: str = Field("", description="章节内容（Markdown格式）")
    level: int = Field(1, ge=1, le=6, description="标题级别（1-6）")
    children: List["PRDSection"] = Field(default_factory=list, description="子章节")
    order: int = Field(0, description="章节顺序")
    expanded: bool = Field(True, description="是否展开（用于前端显示）")

    @model_validator(mode="after")
    def validate_children_level(self) -> "PRDSection":
        """验证子章节级别必须大于父章节"""
        for child in self.children:
            if child.level <= self.level:
                child.level = self.level + 1
        return self

    def to_markdown(self) -> str:
        """将章节转换为Markdown字符串"""
        result = f"{'#' * self.level} {self.title}\n\n"
        if self.content:
            result += f"{self.content}\n\n"
        for child in sorted(self.children, key=lambda c: c.order):
            result += child.to_markdown()
        return result

    def flatten(self) -> List["PRDSection"]:
        """展平为一维列表（包含所有子章节）"""
        result = [self]
        for child in self.children:
            result.extend(child.flatten())
        return result

    def find_section(self, section_id: str) -> Optional["PRDSection"]:
        """查找指定ID的章节"""
        if self.id == section_id:
            return self
        for child in self.children:
            found = child.find_section(section_id)
            if found:
                return found
        return None

    def add_child(self, child: "PRDSection") -> "PRDSection":
        """添加子章节"""
        child.level = self.level + 1
        child.order = len(self.children)
        self.children.append(child)
        return child

    def remove_child(self, section_id: str) -> bool:
        """删除子章节"""
        original_length = len(self.children)
        self.children = [c for c in self.children if c.id != section_id]
        for i, child in enumerate(self.children):
            child.order = i
        return len(self.children) < original_length

    def update_content(self, new_content: str) -> "PRDSection":
        """更新章节内容"""
        self.content = new_content
        return self

    def update_title(self, new_title: str) -> "PRDSection":
        """更新章节标题"""
        self.title = new_title
        return self


class PRDDocument(BaseModel):
    """PRD文档模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="文档唯一标识")
    title: str = Field("产品需求文档", description="文档标题")
    sections: List[PRDSection] = Field(default_factory=list, description="顶层章节列表")
    industry: str = Field("general", description="所属行业")
    created_at: str = Field("", description="创建时间")
    updated_at: str = Field("", description="更新时间")

    @classmethod
    def from_markdown(cls, markdown_text: str) -> "PRDDocument":
        """从Markdown文本解析PRD文档"""
        lines = markdown_text.split('\n')
        sections = []
        stack = []
        
        for line in lines:
            line = line.rstrip('\r')
            
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                section = PRDSection(title=title, level=level)
                
                while stack and stack[-1].level >= level:
                    stack.pop()
                
                if stack:
                    stack[-1].add_child(section)
                else:
                    sections.append(section)
                
                stack.append(section)
                stack[-1].content = ""
            else:
                if stack:
                    if stack[-1].content:
                        stack[-1].content += '\n' + line
                    else:
                        stack[-1].content = line
        
        for i, section in enumerate(sections):
            section.order = i
        
        return cls(sections=sections)

    def to_markdown(self) -> str:
        """将PRD文档转换为Markdown字符串"""
        if self.title:
            result = f"# {self.title}\n\n"
        else:
            result = ""
        
        for section in sorted(self.sections, key=lambda s: s.order):
            result += section.to_markdown()
        
        return result.strip()

    def to_html(self) -> str:
        """将PRD文档转换为HTML（用于实时预览和PDF导出）"""
        return self._generate_html()

    def _generate_html(self) -> str:
        """生成HTML内容"""
        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.title}</title>
    <style>
        :root {{
            --primary-color: #2563eb;
            --secondary-color: #64748b;
            --background-color: #ffffff;
            --card-background: #f8fafc;
            --text-color: #1e293b;
            --border-color: #e2e8f0;
            --heading-color: #0f172a;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
            line-height: 1.8;
            color: var(--text-color);
            background-color: var(--background-color);
            margin: 0;
            padding: 40px 60px;
            max-width: 1200px;
            margin-left: auto;
            margin-right: auto;
        }}
        h1 {{
            font-size: 2.25rem;
            font-weight: 700;
            color: var(--heading-color);
            border-bottom: 3px solid var(--primary-color);
            padding-bottom: 12px;
            margin-bottom: 32px;
        }}
        h2 {{
            font-size: 1.5rem;
            font-weight: 600;
            color: var(--heading-color);
            margin-top: 40px;
            margin-bottom: 16px;
            padding-left: 12px;
            border-left: 4px solid var(--primary-color);
        }}
        h3 {{
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--heading-color);
            margin-top: 32px;
            margin-bottom: 12px;
        }}
        h4, h5, h6 {{
            font-size: 1rem;
            font-weight: 600;
            color: var(--heading-color);
            margin-top: 24px;
            margin-bottom: 8px;
        }}
        p {{
            margin-bottom: 16px;
            text-align: justify;
        }}
        ul, ol {{
            margin-bottom: 16px;
            padding-left: 32px;
        }}
        li {{
            margin-bottom: 8px;
        }}
        li ul, li ol {{
            margin-top: 8px;
            margin-bottom: 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 24px;
            font-size: 0.95rem;
        }}
        th, td {{
            border: 1px solid var(--border-color);
            padding: 12px 16px;
            text-align: left;
        }}
        th {{
            background-color: var(--card-background);
            font-weight: 600;
            color: var(--heading-color);
        }}
        tr:nth-child(even) {{
            background-color: #f8fafc;
        }}
        code {{
            background-color: #f1f5f9;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Fira Code', 'Consolas', monospace;
            font-size: 0.9em;
        }}
        pre {{
            background-color: #1e293b;
            color: #e2e8f0;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            margin-bottom: 16px;
        }}
        pre code {{
            background-color: transparent;
            padding: 0;
            color: inherit;
        }}
        blockquote {{
            border-left: 4px solid var(--secondary-color);
            padding-left: 16px;
            margin: 16px 0;
            color: var(--secondary-color);
            font-style: italic;
        }}
        strong {{
            font-weight: 600;
            color: var(--heading-color);
        }}
        em {{
            font-style: italic;
        }}
        a {{
            color: var(--primary-color);
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .section-card {{
            background-color: var(--card-background);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid var(--border-color);
        }}
        .section-title {{
            margin-top: 0;
            margin-bottom: 12px;
        }}
        .highlight-box {{
            background-color: #fffbeb;
            border-left: 4px solid #f59e0b;
            padding: 16px;
            margin: 16px 0;
            border-radius: 0 8px 8px 0;
        }}
        .warning-box {{
            background-color: #fef2f2;
            border-left: 4px solid #ef4444;
            padding: 16px;
            margin: 16px 0;
            border-radius: 0 8px 8px 0;
        }}
        .info-box {{
            background-color: #eff6ff;
            border-left: 4px solid #3b82f6;
            padding: 16px;
            margin: 16px 0;
            border-radius: 0 8px 8px 0;
        }}
        @media print {{
            body {{
                padding: 20px;
                max-width: none;
            }}
            .no-print {{
                display: none;
            }}
        }}
    </style>
</head>
<body>
"""
        html += self._sections_to_html(self.sections)
        
        html += """
</body>
</html>"""
        
        return html

    def _sections_to_html(self, sections: List[PRDSection]) -> str:
        """将章节列表转换为HTML"""
        html = ""
        
        for section in sorted(sections, key=lambda s: s.order):
            html += self._section_to_html(section)
        
        return html

    def _section_to_html(self, section: PRDSection) -> str:
        """将单个章节转换为HTML"""
        heading_tag = f"h{section.level}"
        content = self._markdown_to_html(section.content)
        
        html = f"""
<div class="section-card">
    <{heading_tag} class="section-title">{section.title}</{heading_tag}>
    <div class="section-content">
{content}
    </div>
"""
        
        if section.children:
            html += """
    <div class="section-children">
"""
            html += self._sections_to_html(section.children)
            html += """
    </div>
"""
        
        html += """
</div>
"""
        
        return html

    def _markdown_to_html(self, markdown: str) -> str:
        """将Markdown内容转换为HTML（简化版）"""
        if not markdown:
            return ""
        
        lines = markdown.split('\n')
        html_lines = []
        in_list = False
        list_type = None
        
        for line in lines:
            if line.startswith('**') and line.endswith('**'):
                html_lines.append(f"<p><strong>{line[2:-2]}</strong></p>")
            elif line.startswith('*') and not line.startswith('**'):
                if not in_list or list_type != 'ul':
                    if in_list:
                        html_lines.append('</ul>')
                    html_lines.append('<ul>')
                    in_list = True
                    list_type = 'ul'
                html_lines.append(f"<li>{line[1:].strip()}</li>")
            elif line.startswith('1. ') or line.startswith('2. ') or re.match(r'^\d+\.', line):
                if not in_list or list_type != 'ol':
                    if in_list:
                        html_lines.append('</ol>')
                    html_lines.append('<ol>')
                    in_list = True
                    list_type = 'ol'
                html_lines.append(f"<li>{re.sub(r'^\d+\.\s*', '', line)}</li>")
            elif line.startswith('> '):
                html_lines.append(f"<blockquote>{line[2:]}</blockquote>")
            elif line.startswith('```'):
                if html_lines and html_lines[-1].startswith('<pre>'):
                    html_lines.append('</pre>')
                else:
                    html_lines.append('<pre><code>')
            elif line.startswith('---'):
                html_lines.append('<hr>')
            elif line.strip() == '':
                if in_list:
                    html_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
            else:
                if in_list:
                    html_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                html_lines.append(f"<p>{line}</p>")
        
        if in_list:
            html_lines.append(f'</{list_type}>')
        
        return '\n'.join(html_lines)

    def find_section(self, section_id: str) -> Optional[PRDSection]:
        """查找指定ID的章节"""
        for section in self.sections:
            found = section.find_section(section_id)
            if found:
                return found
        return None

    def add_section(self, title: str, level: int = 1, content: str = "", parent_id: str = None) -> PRDSection:
        """添加新章节"""
        section = PRDSection(title=title, level=level, content=content)
        
        if parent_id:
            parent = self.find_section(parent_id)
            if parent:
                return parent.add_child(section)
        
        section.order = len(self.sections)
        self.sections.append(section)
        return section

    def update_section(self, section_id: str, **kwargs) -> bool:
        """更新章节内容"""
        section = self.find_section(section_id)
        if not section:
            return False
        
        if 'title' in kwargs:
            section.title = kwargs['title']
        if 'content' in kwargs:
            section.content = kwargs['content']
        if 'level' in kwargs:
            section.level = kwargs['level']
        
        return True

    def delete_section(self, section_id: str) -> bool:
        """删除章节"""
        original_length = len(self.sections)
        self.sections = [s for s in self.sections if s.id != section_id]
        
        for s in self.sections:
            if s.remove_child(section_id):
                return True
        
        return len(self.sections) < original_length

    def reorder_sections(self, section_ids: List[str]) -> bool:
        """重新排序顶层章节"""
        id_to_section = {s.id: s for s in self.sections}
        new_sections = []
        
        for section_id in section_ids:
            if section_id in id_to_section:
                new_sections.append(id_to_section[section_id])
        
        if new_sections:
            self.sections = new_sections
            for i, section in enumerate(self.sections):
                section.order = i
            return True
        
        return False

    def get_section_tree(self) -> List[Dict[str, Any]]:
        """获取章节树的字典表示（用于前端渲染）"""
        return [section.model_dump() for section in self.sections]


PRDSection.model_rebuild()


class PRDDocumentManager:
    """PRD文档管理器"""
    
    @staticmethod
    def parse_markdown(markdown_text: str) -> PRDDocument:
        """解析Markdown为PRD文档"""
        return PRDDocument.from_markdown(markdown_text)

    @staticmethod
    def generate_markdown(document: PRDDocument) -> str:
        """从PRD文档生成Markdown"""
        return document.to_markdown()

    @staticmethod
    def generate_html(document: PRDDocument) -> str:
        """从PRD文档生成HTML"""
        return document.to_html()

    @staticmethod
    def create_empty(industry: str = "general") -> PRDDocument:
        """创建空的PRD文档（带默认章节结构）"""
        from app.data.templates.industry_templates import get_default_sections
        
        sections = []
        default_sections = get_default_sections(industry)
        
        for i, (title, level) in enumerate(default_sections):
            section = PRDSection(title=title, level=level, order=i)
            sections.append(section)
        
        return PRDDocument(sections=sections, industry=industry)

    @staticmethod
    def merge_changes(document: PRDDocument, changes: List[Dict[str, Any]]) -> PRDDocument:
        """批量应用编辑变更"""
        for change in changes:
            action = change.get('action')
            section_id = change.get('section_id')
            
            if action == 'add':
                document.add_section(
                    title=change.get('title', ''),
                    level=change.get('level', 1),
                    content=change.get('content', ''),
                    parent_id=change.get('parent_id')
                )
            elif action == 'update':
                document.update_section(section_id, **change.get('data', {}))
            elif action == 'delete':
                document.delete_section(section_id)
            elif action == 'reorder':
                document.reorder_sections(change.get('section_ids', []))
        
        return document
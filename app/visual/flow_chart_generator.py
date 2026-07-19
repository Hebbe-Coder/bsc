"""
Flow Chart Generator - 业务流程图生成器

基于Mermaid语法生成业务流程图，支持导出为SVG/PNG格式。

生成流程：
1. 解析业务系统数据
2. 生成Mermaid语法
3. 渲染为SVG/PNG（可选，需要mermaid-cli）

支持的图表类型：
- 业务流程图（flowchart）
- 时序图（sequenceDiagram）
- 状态图（stateDiagram）
- 思维导图（mindmap）
"""
from __future__ import annotations
import os
import subprocess
import tempfile
from typing import Dict, Any, Optional


class FlowChartGenerator:
    """业务流程图生成器"""
    
    def __init__(self):
        self._mermaid_cli_path = self._find_mermaid_cli()
    
    def _find_mermaid_cli(self) -> Optional[str]:
        """查找mermaid-cli路径"""
        try:
            result = subprocess.run(
                ["npx", "mmdc", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return "npx mmdc"
        except Exception:
            pass
        
        try:
            result = subprocess.run(
                ["mmdc", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return "mmdc"
        except Exception:
            pass
        
        return None
    
    def generate_flowchart(self, business_system: Dict[str, Any]) -> str:
        """生成业务流程图Mermaid代码"""
        workflow = business_system.get("workflow", [])
        objectives = business_system.get("objectives", [])
        domain = business_system.get("business_domain", "")
        
        nodes = {}
        edges = []
        
        for idx, step in enumerate(workflow, 1):
            node_id = f"step{idx}"
            node_label = step.get("name", f"步骤{idx}")
            nodes[node_id] = node_label
            
            if idx > 1:
                edges.append((f"step{idx-1}", node_id))
        
        mermaid_lines = [
            "flowchart TD",
            "    classDef start fill:#4CAF50,color:#fff",
            "    classDef process fill:#2196F3,color:#fff",
            "    classDef end fill:#f44336,color:#fff",
            "",
        ]
        
        for node_id, label in nodes.items():
            if node_id == "step1":
                mermaid_lines.append(f"    {node_id}[{label}]:::start")
            elif node_id == f"step{len(workflow)}":
                mermaid_lines.append(f"    {node_id}[{label}]:::end")
            else:
                mermaid_lines.append(f"    {node_id}[{label}]:::process")
        
        mermaid_lines.append("")
        for from_node, to_node in edges:
            mermaid_lines.append(f"    {from_node} --> {to_node}")
        
        mermaid_lines.append("\n    subgraph 业务目标\n")
        for obj in objectives[:3]:
            obj_text = obj.get("objective", "")
            if obj_text:
                mermaid_lines.append(f"        obj_{obj_text[:10]}[\"{obj_text}\"]")
        mermaid_lines.append("    end")
        
        if domain:
            mermaid_lines.append("\n    style subgraph fill:#f5f5f5,stroke:#ccc\n")
        
        return "\n".join(mermaid_lines)
    
    def generate_mindmap(self, business_system: Dict[str, Any]) -> str:
        """生成思维导图Mermaid代码"""
        domain = business_system.get("business_domain", "业务系统")
        objectives = business_system.get("objectives", [])
        workflow = business_system.get("workflow", [])
        modules = business_system.get("modules", [])
        risks = business_system.get("risks", [])
        
        mermaid_lines = [
            "mindmap",
            f"    root(({domain}))",
            "",
        ]
        
        if objectives:
            mermaid_lines.append("        业务目标")
            for obj in objectives[:5]:
                obj_text = obj.get("objective", "")
                target = obj.get("target", "")
                if obj_text:
                    label = f"{obj_text}"
                    if target:
                        label += f"\\n目标: {target}"
                    mermaid_lines.append(f"            {label}")
        
        if workflow:
            mermaid_lines.append("        业务流程")
            for step in workflow[:8]:
                step_name = step.get("name", "")
                if step_name:
                    mermaid_lines.append(f"            {step_name}")
        
        if modules:
            mermaid_lines.append("        核心模块")
            for module in modules[:5]:
                module_name = module.get("name", "")
                if module_name:
                    mermaid_lines.append(f"            {module_name}")
        
        if risks:
            mermaid_lines.append("        风险分析")
            for risk in risks[:5]:
                risk_name = risk.get("risk", "")
                level = risk.get("level", "")
                if risk_name:
                    label = f"{risk_name}"
                    if level:
                        label += f" ({level})"
                    mermaid_lines.append(f"            {label}")
        
        return "\n".join(mermaid_lines)
    
    def generate_sequence_diagram(self, business_system: Dict[str, Any]) -> str:
        """生成时序图Mermaid代码"""
        workflow = business_system.get("workflow", [])
        roles = business_system.get("roles", [])
        
        participants = set()
        for step in workflow:
            actor = step.get("actor", step.get("role", ""))
            if actor:
                participants.add(actor)
        
        for role in roles[:5]:
            role_name = role.get("role", "")
            if role_name:
                participants.add(role_name)
        
        if not participants:
            participants = {"用户", "系统", "外部服务"}
        
        mermaid_lines = [
            "sequenceDiagram",
            "    participant 用户",
            "",
        ]
        
        for participant in participants:
            if participant != "用户":
                mermaid_lines.append(f"    participant {participant}")
        
        mermaid_lines.append("")
        
        for idx, step in enumerate(workflow[:15], 1):
            actor = step.get("actor", step.get("role", "用户"))
            action = step.get("name", f"步骤{idx}")
            next_step = step.get("next", "")
            
            if idx % 2 == 1:
                mermaid_lines.append(f"    {actor}->>系统: {action}")
            else:
                mermaid_lines.append(f"    系统-->>{actor}: {action}")
            
            if next_step:
                mermaid_lines.append(f"    Note right of 系统: 下一步: {next_step}")
        
        mermaid_lines.append("")
        mermaid_lines.append("    Note over 用户,系统: 业务流程完成")
        
        return "\n".join(mermaid_lines)
    
    def generate_state_diagram(self, business_system: Dict[str, Any]) -> str:
        """生成状态图Mermaid代码"""
        workflow = business_system.get("workflow", [])
        risks = business_system.get("risks", [])
        
        if not workflow:
            return "stateDiagram-v2\n    [*] --> 空闲\n    空闲 --> 处理中\n    处理中 --> 完成\n    完成 --> [*]"
        
        mermaid_lines = [
            "stateDiagram-v2",
            "",
        ]
        
        step_names = []
        for idx, step in enumerate(workflow[:10], 1):
            step_name = step.get("name", f"状态{idx}")
            step_names.append(step_name)
        
        mermaid_lines.append(f"    [*] --> {step_names[0]}")
        
        for i in range(len(step_names) - 1):
            mermaid_lines.append(f"    {step_names[i]} --> {step_names[i+1]}")
        
        mermaid_lines.append(f"    {step_names[-1]} --> 完成")
        mermaid_lines.append("    完成 --> [*]")
        
        if risks:
            mermaid_lines.append("")
            mermaid_lines.append("    state 异常处理 {")
            for risk in risks[:3]:
                risk_name = risk.get("risk", "")
                if risk_name:
                    mermaid_lines.append(f"        [{risk_name}]")
            mermaid_lines.append("    }")
            
            mermaid_lines.append("")
            for risk in risks[:3]:
                risk_name = risk.get("risk", "")
                if risk_name:
                    mermaid_lines.append(f"    {step_names[0]} --> [{risk_name}]: 异常")
                    mermaid_lines.append(f"    [{risk_name}] --> {step_names[0]}: 恢复")
        
        return "\n".join(mermaid_lines)
    
    def render_to_svg(self, mermaid_code: str, output_path: str = None) -> str:
        """将Mermaid代码渲染为SVG"""
        if not self._mermaid_cli_path:
            raise RuntimeError("mermaid-cli未安装，请运行: npm install -g @mermaid-js/mermaid-cli")
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False) as f:
            f.write(mermaid_code)
            input_file = f.name
        
        try:
            if output_path is None:
                output_path = input_file.replace(".mmd", ".svg")
            
            result = subprocess.run(
                f"{self._mermaid_cli_path} -i {input_file} -o {output_path}".split(),
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Mermaid渲染失败: {result.stderr}")
            
            return output_path
        finally:
            if os.path.exists(input_file):
                os.unlink(input_file)
    
    def render_to_png(self, mermaid_code: str, output_path: str = None) -> str:
        """将Mermaid代码渲染为PNG"""
        if not self._mermaid_cli_path:
            raise RuntimeError("mermaid-cli未安装，请运行: npm install -g @mermaid-js/mermaid-cli")
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False) as f:
            f.write(mermaid_code)
            input_file = f.name
        
        try:
            if output_path is None:
                output_path = input_file.replace(".mmd", ".png")
            
            result = subprocess.run(
                f"{self._mermaid_cli_path} -i {input_file} -o {output_path} -f png".split(),
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Mermaid渲染失败: {result.stderr}")
            
            return output_path
        finally:
            if os.path.exists(input_file):
                os.unlink(input_file)
    
    def generate_all(self, business_system: Dict[str, Any]) -> Dict[str, str]:
        """生成所有类型的图表"""
        return {
            "flowchart": self.generate_flowchart(business_system),
            "mindmap": self.generate_mindmap(business_system),
            "sequence_diagram": self.generate_sequence_diagram(business_system),
            "state_diagram": self.generate_state_diagram(business_system),
        }
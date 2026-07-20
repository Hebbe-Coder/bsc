"""
BSC CLI — 命令行入口

借鉴 Grok Build 多运行模式:
  - bsc compile prd.md          → 编译 PRD (Headless 模式)
  - bsc compile prd.md --watch  → 监视文件变化自动编译
  - bsc serve                   → 启动 HTTP 服务
  - bsc list-formats            → 列出可用导出格式
  - bsc health                  → 健康检查

使用:
    python -m app.cli compile input.md --output html,ppt
    python -m app.cli serve --port 8000
"""

import argparse
import sys
import os
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        prog="bsc",
        description="BSC Studio — Business System Compiler CLI",
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # ── compile ──
    compile_parser = sub.add_parser("compile", help="编译 PRD 为 Business System")
    compile_parser.add_argument("input", help="PRD 文件路径或直接文本")
    compile_parser.add_argument(
        "-o", "--output", default="html,json",
        help="输出格式, 逗号分隔 (默认: html,json)"
    )
    compile_parser.add_argument(
        "-t", "--template", default=None,
        help="行业模板 ID"
    )
    compile_parser.add_argument(
        "--watch", action="store_true",
        help="监视文件变化自动重新编译"
    )
    compile_parser.add_argument(
        "--timeout", type=int, default=300,
        help="单次编译超时秒数 (默认: 300)"
    )

    # ── serve ──
    serve_parser = sub.add_parser("serve", help="启动 HTTP API 服务")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")

    # ── health ──
    sub.add_parser("health", help="健康检查")

    # ── list-formats ──
    sub.add_parser("list-formats", help="列出可用导出格式")

    # ── info ──
    sub.add_parser("info", help="显示项目信息")

    # -- agent --
    agent_parser = sub.add_parser("agent", help="Business Agent OS")
    agent_parser.add_argument("input", help="PRD file or text")
    agent_parser.add_argument("-m", "--mode", default="llm", choices=["llm", "template", "static"])
    agent_parser.add_argument("--domain", default="")
    agent_parser.add_argument("--board", action="store_true")
    agent_parser.add_argument("-o", "--output", default="report.json")
    agent_parser.add_argument("--no-llm", action="store_true")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    if args.command == "compile":
        cmd_compile(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "health":
        cmd_health()
    elif args.command == "list-formats":
        cmd_list_formats()
    elif args.command == "info":
        cmd_info()
    elif args.command == "agent":
        cmd_agent(args)


def cmd_compile(args):
    """编译 PRD"""
    # 读取输入
    input_path = Path(args.input)
    if input_path.exists():
        print(f"📄 Reading: {input_path}")
        content = input_path.read_text(encoding="utf-8")
    else:
        content = args.input

    if len(content.strip()) < 10:
        print("❌ Error: Input too short (min 10 chars)")
        sys.exit(1)

    # 编译
    print("🔄 Compiling...")
    from app.capabilities.runner import run_legacy_bsc_runtime_sync

    try:
        result = run_legacy_bsc_runtime_sync(
            input_text=content,
            template_id=args.template,
            async_mode=False,
        )
    except Exception as e:
        print(f"❌ Compilation failed: {e}")
        sys.exit(1)

    bs = result.get("business_system", {})
    domain = bs.get("business_domain", "unknown")
    pipeline_info = result.get("pipeline", {})

    # 显示摘要
    stages = pipeline_info.get("stages", [])
    print(f"\n✅ Compilation complete!")
    print(f"   Domain: {domain}")
    print(f"   Stages: {len(stages)}")
    for s in stages:
        status_icon = "✅" if s.get("status") == "success" else "❌"
        print(f"     {status_icon} {s.get('display', s.get('key', '[ERR]'))} "
              f"({s.get('duration_ms', 0):.0f}ms)")

    # 导出
    formats = [f.strip() for f in args.output.split(",")]
    print(f"\n📦 Exporting to: {', '.join(formats)}")

    from exporters.bridge import ExportBridge

    results = ExportBridge.export_all(bs, formats)
    for fmt, r in results.items():
        icon = "✅" if r.success else "❌"
        info = r.path or r.error
        print(f"   {icon} {fmt}: {info}")

    # 输出目录
    output_dir = Path("output")
    if output_dir.exists():
        print(f"\n📁 Output files in: {output_dir.absolute()}")


def cmd_serve(args):
    """启动 HTTP 服务"""
    import uvicorn
    print(f"🚀 Starting BSC server at http://{args.host}:{args.port}")
    print(f"   Docs: http://{args.host}:{args.port}/docs")
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def cmd_health():
    """健康检查"""
    from app.core.config import settings
    from app.repositories import ProjectRepository
    from app.services.llm_service import LLMService

    print("🏥 BSC Health Check")
    print(f"   App: {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"   Environment: {settings.ENVIRONMENT}")
    print(f"   LLM Provider: {settings.LLM_PROVIDER}")

    try:
        db_ok = ProjectRepository.test_connection()
        print(f"   Database: {'✅' if db_ok else '❌'}")
    except Exception as e:
        print(f"   Database: ❌ ({e})")

    try:
        llm = LLMService()
        print(f"   LLM Service: {'✅' if llm.is_ready() else '⚠️  not ready'}")
    except Exception as e:
        print(f"   LLM Service: ❌ ({e})")

    from exporters.bridge import ExportBridge
    fmts = ExportBridge.list_formats()
    print(f"   Export formats: {len(fmts)} available")


def cmd_list_formats():
    """列出导出格式"""
    from exporters.bridge import ExportBridge
    fmts = ExportBridge.list_formats()
    print(f"Available export formats ({len(fmts)}):")
    for f in fmts:
        aliases = f.get("aliases", [])
        alias_str = f" (aliases: {', '.join(aliases)})" if aliases else ""
        print(f"  {f['format']:12s} → {f['description']}{alias_str}")

def cmd_agent(args):
    """Business Agent OS ? ??????"""
    import asyncio, json, time
    from pathlib import Path

    input_path = Path(args.input)
    if input_path.exists():
        print(f"Reading: {input_path}")
        content_text = input_path.read_text(encoding="utf-8")
    else:
        content_text = args.input

    if len(content_text.strip()) < 10:
        print("Error: Input too short (min 10 chars)")
        sys.exit(1)

    from app.capabilities.runner import run_business_runtime
    from app.core.config import settings

    t0 = time.perf_counter()
    print(f"Agent OS: Planning with mode={args.mode}...")

    async def run():
        response = await run_business_runtime(
            input_text=content_text,
            domain=args.domain,
            mode=args.mode,
            board=args.board,
            tenant_id=settings.DEFAULT_TENANT_ID,
        )
        if response["status"] != "completed":
            raise RuntimeError(response.get("runtime", {}).get("errors") or "Agent OS failed")

        mission = response["mission"]
        runtime = response["runtime"]
        print(f"  Mission: {mission['title']} ({mission['steps']} steps)")
        print(f"  Gaps found: {response['gaps']}")
        if response.get("board_verdict"):
            print(
                f"  Board Verdict: {response['board_verdict'].upper()} "
                f"({response['board_consensus']})"
            )

        export_data = response["report"]
        export_data["mission"] = mission
        export_data["runtime"] = runtime
        if response.get("board"):
            export_data["board"] = response["board"]

        output_path = Path(args.output)
        output_path.write_text(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  Report saved: {output_path.absolute()}")

        elapsed = (time.perf_counter() - t0)
        print(f"\nAgent OS complete in {elapsed:.1f}s")
        print(f"  Artifacts: {response['artifacts']}")
        print(f"  Gaps: {response['gaps']}")
        if response.get("board_verdict"):
            print(f"  Board: {response['board_verdict']} ({response['board_consensus']})")

    asyncio.run(run())


def cmd_info():
    """显示项目信息"""
    from app.core.config import settings
    from app.enums import PipelineStage, LLMProvider

    print("📋 BSC Studio Project Info")
    print(f"   Version: {settings.APP_VERSION}")
    print(f"   Environment: {settings.ENVIRONMENT}")
    print(f"   LLM Providers: {', '.join(LLMProvider)}")
    print(f"   Pipeline Stages: {', '.join(PipelineStage)}")

    # 统计
    from pathlib import Path
    app_dir = Path(__file__).parent.parent / "app"
    py_files = list(app_dir.rglob("*.py"))
    print(f"   Python files (app/): {len(py_files)}")

    from exporters.bridge import ExportBridge
    print(f"   Export formats: {len(ExportBridge.list_formats())}")


if __name__ == "__main__":
    main()

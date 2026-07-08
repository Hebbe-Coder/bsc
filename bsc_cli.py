#!/usr/bin/env python3
"""
BSC CLI - 命令行工具

支持对话式需求确认，提供交互式和非交互式两种模式：

交互式模式：
    bsc_cli dialog --input "我要做一个电商系统" --depth medium

非交互式模式：
    bsc_cli dialog --input "电商系统" --auto --output prd.md

快速生成：
    bsc_cli quick --input "电商系统"
"""
import argparse
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_dialog_interactive(args):
    """运行交互式对话"""
    from app.core.dialog_engine import DialogEngine
    
    engine = DialogEngine()
    
    user_id = args.user_id or f"cli_user_{uuid.uuid4().hex[:8]}"
    input_text = args.input
    
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                input_text = f.read()
        except Exception as e:
            print(f"❌ 读取文件失败: {e}")
            return
    
    if not input_text:
        input_text = input("请输入产品描述: ")
    
    print(f"\n🤖 已识别输入：{input_text[:50]}..." if len(input_text) > 50 else f"\n🤖 已识别输入：{input_text}")
    print(f"🤖 对话深度：{args.depth}模式")
    
    session = engine.create_session(user_id, input_text, args.depth, args.industry)
    
    if "error" in session:
        print(f"❌ 创建会话失败: {session['error']}")
        return
    
    session_id = session["session_id"]
    total_questions = session["total_questions"]
    
    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    while True:
        session_data = engine.get_session_status(session_id)
        
        if not session_data:
            print("❌ 会话不存在")
            break
        
        if session_data["status"] == "completed":
            break
        
        messages = session_data["messages"]
        if not messages:
            break
        
        last_msg = messages[-1]
        
        if last_msg["answer"]:
            next_result = engine.answer_question(session_id, last_msg["answer"])
            
            if "error" in next_result:
                print(f"❌ 错误: {next_result['error']}")
                break
            
            if next_result["status"] == "completed":
                print("\n✅ 需求收集完成！")
                break
            
            last_msg = {
                "question": next_result["next_question"],
                "question_key": next_result["question_key"],
                "question_number": next_result["question_number"],
            }
        
        print(f"\n问题 {last_msg['question_number']}/{total_questions}：{last_msg['question']}")
        answer = input("> ")
        
        engine.add_dialog_message(
            session_id,
            last_msg["question_key"],
            last_msg["question"],
            answer,
            last_msg["question_number"]
        )
        
        collected_data = session_data.get("collected_data", {}).copy()
        collected_data[last_msg["question_key"]] = answer
        engine.db.update_dialog_session(session_id, collected_data=collected_data)
    
    complete_result = engine.complete_session(session_id)
    
    if args.output:
        output_path = args.output
    else:
        output_path = f"output/prd_{session_id[:8]}.md"
    
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(complete_result.get("prd_text", ""))
    
    print(f"\n📝 生成的PRD已保存到：{output_path}")
    
    if args.compile:
        print("\n🔧 正在编译...")
        
        try:
            from app.core.bsc_pipeline import compile_to_business_system
            
            bs = compile_to_business_system(complete_result["prd_text"])
            
            bs_output = f"output/business_system_{session_id[:8]}.json"
            import json
            with open(bs_output, 'w', encoding='utf-8') as f:
                json.dump(bs, f, ensure_ascii=False, indent=2)
            
            print(f"🚀 编译完成！")
            print(f"📊 业务系统已保存到：{bs_output}")
        except Exception as e:
            print(f"❌ 编译失败: {e}")


def run_dialog_auto(args):
    """运行自动模式"""
    from app.core.dialog_engine import DialogEngine
    
    engine = DialogEngine()
    
    user_id = args.user_id or f"cli_user_{uuid.uuid4().hex[:8]}"
    input_text = args.input
    
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                input_text = f.read()
        except Exception as e:
            print(f"❌ 读取文件失败: {e}")
            return
    
    if not input_text:
        print("❌ 请提供输入文本或文件")
        return
    
    print(f"🤖 快速生成PRD...")
    
    session = engine.create_session(user_id, input_text, args.depth, args.industry)
    
    if "error" in session:
        print(f"❌ 创建会话失败: {session['error']}")
        return
    
    complete_result = engine.complete_session(session["session_id"])
    
    if args.output:
        output_path = args.output
    else:
        output_path = f"output/prd_{session['session_id'][:8]}.md"
    
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(complete_result.get("prd_text", ""))
    
    print(f"✅ PRD已生成：{output_path}")


def run_quick_generate(args):
    """快速生成PRD（不经过对话）"""
    from app.engines.prd_analyzer import PRDAnalyzer
    
    analyzer = PRDAnalyzer()
    
    input_text = args.input
    
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                input_text = f.read()
        except Exception as e:
            print(f"❌ 读取文件失败: {e}")
            return
    
    if not input_text:
        print("❌ 请提供输入文本或文件")
        return
    
    print(f"🔍 分析输入...")
    
    analysis = analyzer.analyze(input_text)
    
    prd_text = f"""# {input_text}

## 基本信息
- 行业：{analysis["industry"]}
- PRD质量：{analysis["prd_quality"]}%

## 业务目标
根据分析，此产品的业务目标需要进一步明确。

## 核心功能
根据分析，核心功能需要进一步明确。

## 缺失章节
{chr(10).join([f"- {s}" for s in analysis.get("missing_sections", [])])}

## 建议
{chr(10).join([f"- {r['suggestion']}" for r in analysis["recommendations"]])}"""
    
    if args.output:
        output_path = args.output
    else:
        import uuid
        output_path = f"output/prd_quick_{uuid.uuid4().hex[:8]}.md"
    
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(prd_text)
    
    print(f"✅ 快速PRD已生成：{output_path}")
    print(f"📊 行业：{analysis['industry']} | 质量评分：{analysis['prd_quality']}%")


def run_preferences(args):
    """管理用户偏好"""
    from app.core.user_preference_service import UserPreferenceService
    
    service = UserPreferenceService()
    user_id = args.user_id or f"cli_user_{uuid.uuid4().hex[:8]}"
    
    if args.action == "get":
        prefs = service.get_preferences(user_id)
        import json
        print(json.dumps(prefs, ensure_ascii=False, indent=2))
    
    elif args.action == "set":
        if args.key and args.value:
            category, key = args.key.split(".", 1)
            success = service.set_preference(user_id, category, key, args.value)
            print(f"✅ 偏好设置成功" if success else "❌ 偏好设置失败")
    
    elif args.action == "reset":
        success = service.reset_preferences(user_id)
        print(f"✅ 偏好已重置" if success else "❌ 重置失败")
    
    elif args.action == "profile":
        profile = service.get_user_profile(user_id)
        import json
        print(json.dumps(profile, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="BSC CLI - 业务系统编译器命令行工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    dialog_parser = subparsers.add_parser("dialog", help="对话式需求确认")
    dialog_parser.add_argument("--input", "-i", type=str, help="输入文本")
    dialog_parser.add_argument("--file", "-f", type=str, help="输入文件")
    dialog_parser.add_argument("--depth", "-d", type=str, default="medium", 
                               choices=["light", "medium", "deep"], help="对话深度")
    dialog_parser.add_argument("--industry", "-n", type=str, default="general", help="行业类型")
    dialog_parser.add_argument("--user-id", "-u", type=str, help="用户ID")
    dialog_parser.add_argument("--output", "-o", type=str, help="输出文件路径")
    dialog_parser.add_argument("--compile", "-c", action="store_true", help="是否编译")
    dialog_parser.add_argument("--auto", "-a", action="store_true", help="自动模式（跳过交互）")
    
    quick_parser = subparsers.add_parser("quick", help="快速生成PRD")
    quick_parser.add_argument("--input", "-i", type=str, help="输入文本")
    quick_parser.add_argument("--file", "-f", type=str, help="输入文件")
    quick_parser.add_argument("--output", "-o", type=str, help="输出文件路径")
    
    pref_parser = subparsers.add_parser("preferences", help="管理用户偏好")
    pref_parser.add_argument("action", type=str, choices=["get", "set", "reset", "profile"])
    pref_parser.add_argument("--user-id", "-u", type=str, help="用户ID")
    pref_parser.add_argument("--key", "-k", type=str, help="偏好键（格式：category.key）")
    pref_parser.add_argument("--value", "-v", type=str, help="偏好值")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == "dialog":
            if args.auto:
                run_dialog_auto(args)
            else:
                run_dialog_interactive(args)
        
        elif args.command == "quick":
            run_quick_generate(args)
        
        elif args.command == "preferences":
            run_preferences(args)
    
    except KeyboardInterrupt:
        print("\n\n👋 操作已取消")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

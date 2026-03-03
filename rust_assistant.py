import os
import sys
from dotenv import load_dotenv
from project import RustProject
from llm import LLMClient
from algorithm import rust_assistant as run_algorithm


def load_api_config() -> tuple:
    """
    从.env文件加载API配置（密钥和基础URL）
    
    Returns:
        (API密钥字符串, base_url字符串) 元组
    """
    # 加载.env文件
    load_dotenv()
    
    # 从环境变量获取API密钥
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key is None:
        print("Warning: OPENAI_API_KEY not found in .env file. Using default value.")
        api_key = "your_api_key_here"
    
    # 从环境变量获取base_url，如果未设置则为None
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url and base_url.strip():
        print(f"Using custom base URL: {base_url}")
    
    return api_key, base_url


def main():
    """主函数"""
    # 解析命令行参数
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <rust_project_path>")
        sys.exit(1)
    
    project_path = sys.argv[1]
    
    # 验证项目路径
    if not os.path.exists(project_path):
        print(f"Project path does not exist: {project_path}")
        sys.exit(1)
    
    # 验证是否是Rust项目（检查Cargo.toml文件）
    cargo_toml_path = os.path.join(project_path, "Cargo.toml")
    if not os.path.exists(cargo_toml_path):
        print(f"Not a Rust project: Cargo.toml not found at {project_path}")
        sys.exit(1)
    
    print(f"Starting RustAssistant on project: {project_path}")
    print("=" * 80)
    
    # 初始化项目和LLM客户端
    project = RustProject(project_path)
    api_key, base_url = load_api_config()
    llm = LLMClient(model="gpt-4", api_key=api_key, base_url=base_url)
    
    # 运行算法
    try:
        success = run_algorithm(llm, 3, project)
        
        print("=" * 80)
        if success:
            print("✅ Successfully fixed all errors in the Rust project!")
        else:
            print("❌ Failed to fix all errors in the Rust project.")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
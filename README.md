# RustAssistant

RustAssistant 是一个自动化的 Rust 代码修复工具，使用 LLM（大型语言模型）来识别和修复 Rust 项目中的编译错误。该工具实现了 RUSTASSISTANT 算法，能够循环检测错误、调用 LLM 生成修复方案并应用补丁。

## 功能特点

- 自动检测 Rust 项目中的编译错误
- 使用 LLM 生成多个修复方案
- 智能选择最佳修复方案并应用
- 支持错误处理和回滚机制
- 模块化设计，易于扩展

## 项目结构

```
RustAssistant/
├── rust_assistant.py  # 主入口文件
├── utils.py           # 数据类和工具函数
├── project.py         # Rust项目管理
├── llm.py             # LLM客户端
├── algorithm.py       # 核心算法实现
├── requirements.txt   # 依赖声明
└── README.md          # 项目说明
```

## 安装

1. 确保已经安装 Python 3.8 或更高版本
2. 克隆或下载本项目到本地
3. 安装依赖：

```bash
pip install -r requirements.txt
```

4. 准备 API 密钥：
   - 在 `rust_assistant.py` 中修改 `load_api_key()` 函数，提供您的 LLM API 密钥
   - 或者使用 python-dotenv 从环境变量加载

## 使用方法

基本用法：

```bash
python rust_assistant.py <rust_project_path>
```

参数说明：
- `<rust_project_path>`: Rust 项目的路径（包含 Cargo.toml 的目录）

示例：

```bash
python rust_assistant.py /path/to/your/rust/project
```

## 工作原理

RustAssistant 按照以下步骤工作：

1. 检查 Rust 项目中的错误
2. 当错误集不为空时，循环处理每个错误
3. 为每个错误选择一个初始错误进行处理
4. 创建项目快照以便在需要时回滚
5. 循环处理新出现的错误：
   - 选择一个错误
   - 实例化提示并调用 LLM
   - 获取多个补全方案并选择最佳方案
   - 应用修复补丁
   - 检查新出现的错误
   - 如果需要放弃，恢复到之前的快照
6. 更新错误集并继续循环，直到所有错误都被修复或达到最大尝试次数

## 配置选项

在 `project.py` 中可以调整以下配置：

- `max_attempts`: 最大尝试次数（默认：10）
- `max_time`: 最大执行时间（秒，默认：600）

## 注意事项

1. 请确保已正确设置 LLM API 密钥
2. 工具需要 `cargo` 命令行工具可用
3. 对于复杂的错误，可能需要多次尝试或人工干预
4. 建议在应用修复前备份重要项目

## 故障排除

- 如果 API 调用失败，请检查网络连接和 API 密钥
- 如果修复失败，可能需要调整提示模板或 LLM 模型参数
- 如果工具运行时间过长，可以调整 `max_time` 参数

## 扩展开发

可以通过以下方式扩展功能：

1. 修改 `llm.py` 中的 `invoke()` 方法使用不同的 LLM API
2. 更新 `algorithm.py` 中的算法以改进错误处理策略
3. 添加更多的错误分析和补丁验证功能

## 许可证

[在此添加许可证信息]
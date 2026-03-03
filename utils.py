import os
import json
import subprocess
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class ErrorInfo:
    """错误信息的数据类"""
    message: str
    line: Optional[int] = None
    file: Optional[str] = None
    code: Optional[str] = None

    def __eq__(self, other):
        if not isinstance(other, ErrorInfo):
            return False
        # 根据算法描述，错误比较基于：错误码 + 错误消息 + 文件名
        # 不包含行号信息
        return (
            self.message == other.message and
            self.file == other.file and
            self.code == other.code
        )

    def __hash__(self):
        # 哈希值也基于相同的字段
        return hash((self.message, self.file, self.code))


@dataclass
class Completion:
    """代码补全的数据类"""
    content: str
    confidence: float
    file_path: str
    line_start: int
    line_end: int

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Completion':
        """从字典创建实例"""
        return cls(**data)


def parse_cargo_error(stderr: str) -> List[ErrorInfo]:
    """解析Cargo错误输出，使用更健壮的正则表达式提取错误位置信息"""
    print(f"[DEBUG] 原始错误输出: {stderr[:500]}...")  # 添加调试日志
    errors = []
    import re
    
    # 首先，从输出中提取所有错误区块
    error_blocks = []
    current_block = None
    
    for line in stderr.split('\n'):
        line = line.strip()
        
        # 检查是否是新的错误区块的开始
        error_match = re.search(r'error\[(E\d+)\]: (.+)', line)
        if error_match:
            # 如果有当前区块，保存它
            if current_block:
                error_blocks.append(current_block)
            # 开始新的区块
            current_block = {
                'message': error_match.group(2).strip(),
                'code': error_match.group(1),
                'location': None,
                'code_snippet': ''
            }
        # 检查是否包含位置信息 (适配多种格式)
        elif current_block and not current_block.get('location'):
            # 匹配更灵活的位置格式，包括多种可能的分隔符和空格
            location_patterns = [
                r'-->([^:]+\.rs):(\d+)',  # --> file.rs:123
                r'([^:\n]+\.rs):(\d+):(\d+):',  # file.rs:123:45: error
                r'([^:\n]+\.rs):(\d+):',  # file.rs:123:
            ]
            
            matched = False
            for pattern in location_patterns:
                location_match = re.search(pattern, line)
                if location_match:
                    current_block['location'] = {
                        'file': location_match.group(1).strip(),
                        'line': int(location_match.group(2))
                    }
                    matched = True
                    break
            
            if matched:
                print(f"[DEBUG] 找到位置信息: {current_block['location']}")
        # 检查是否包含代码信息
        elif current_block:
            # 尝试提取代码行
            code_match = re.search(r'\s*\d+\s*\|\s*(.+)', line)
            if code_match:
                current_block['code_snippet'] = code_match.group(1).strip()
    
    # 添加最后一个区块
    if current_block:
        error_blocks.append(current_block)
    
    print(f"[DEBUG] 找到 {len(error_blocks)} 个错误区块")
    
    # 处理所有找到的错误区块
    for block in error_blocks:
        file_path = block['location']['file'] if block.get('location') else None
        line_num = block['location']['line'] if block.get('location') else None
        
        # 组合完整错误消息
        full_message = block['message']
        if block.get('code_snippet'):
            full_message += f"\n代码: {block['code_snippet']}"
        
        errors.append(ErrorInfo(
            message=full_message,
            line=line_num,
            file=file_path,
            code=block.get('code')
        ))
    
    # 如果没有找到结构化错误区块，回退到JSON解析
    if not errors:
        print("[DEBUG] 尝试JSON解析...")
        for line in stderr.strip().split('\n'):
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get('reason') == 'compiler-message' and data.get('message', {}).get('level') == 'error':
                    msg = data['message']
                    
                    # 提取主要错误消息
                    main_message = msg.get('message', '')
                    
                    # 提取错误信息详情
                    message_parts = [main_message]
                    if msg.get('spans'):
                        for span in msg['spans']:
                            if 'label' in span:
                                message_parts.append(f"{span['label']}")
                            for part in span.get('text', []):
                                if 'text' in part:
                                    message_parts.append(part['text'])
                    
                    message = '\n'.join(message_parts)
                    
                    # 提取文件和行号
                    file = None
                    line_num = None
                    if msg.get('spans') and msg['spans'][0]:
                        span = msg['spans'][0]
                        file = span.get('file_name')
                        line_num = span.get('line_start')
                    
                    error = ErrorInfo(
                        message=message,
                        file=file,
                        line=line_num,
                        code=msg.get('code', {}).get('code')
                    )
                    errors.append(error)
                    print(f"[DEBUG] JSON解析成功: {error}")
            except json.JSONDecodeError:
                continue
    
    # 如果仍然没有解析到具体错误，但是有错误提示，创建一个通用错误
    if not errors and 'error:' in stderr:
        print("[DEBUG] 使用通用错误提取...")
        # 尝试从整体输出中提取错误消息
        error_msg_match = re.search(r'error(?:\[E\d+\])?: ([^\n]+)', stderr)
        error_msg = error_msg_match.group(1) if error_msg_match else "编译错误，请检查代码"
        
        # 尝试从整体输出中提取位置信息，使用更灵活的正则表达式
        file = None
        line_num = None
        
        # 尝试多种位置格式
        location_matches = re.findall(r'([^:\n]+\.rs):(\d+)', stderr)
        if location_matches:
            file, line_num = location_matches[0]
            line_num = int(line_num)
            print(f"[DEBUG] 从整体输出中提取位置: {file}:{line_num}")
        else:
            # 如果找不到具体位置，默认为src/main.rs第1行
            print("[DEBUG] 找不到具体位置，使用默认值")
            file = "src/main.rs"
            line_num = 1
        
        # 尝试提取错误代码
        code_match = re.search(r'error\[(E\d+)\]', stderr)
        code = code_match.group(1) if code_match else None
        
        errors.append(ErrorInfo(
            message=error_msg,
            file=file,
            line=line_num,
            code=code
        ))
    
    # 如果仍然没有错误，检查是否有编译失败的迹象
    if not errors:
        print("[DEBUG] 创建默认错误...")
        errors.append(ErrorInfo(
            message="编译失败，无法解析具体错误",
            file="src/main.rs",  # 默认文件
            line=1,  # 默认行号
            code=None
        ))
    
    print(f"[DEBUG] 最终解析到 {len(errors)} 个错误")
    for error in errors:
        print(f"[DEBUG] 错误: {error.code}: {error.message[:50]}... at {error.file}:{error.line}")
    
    return errors


def read_file(file_path: str, encoding: str = 'utf-8') -> Optional[str]:
    """安全地读取文件内容"""
    try:
        with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return None


def write_file(file_path: str, content: str, encoding: str = 'utf-8') -> bool:
    """安全地写入文件内容"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding=encoding) as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error writing file {file_path}: {e}")
        return False


def run_command(command: List[str], cwd: Optional[str] = None, timeout: int = 60) -> subprocess.CompletedProcess:
    """运行命令并返回结果"""
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding='utf-8',
        timeout=timeout
    )


def format_prompt(error: ErrorInfo) -> str:
    """格式化提示信息"""
    prompt_parts = [
        "Fix the following Rust error:\n"
    ]
    
    if error.code:
        prompt_parts.append(f"Error code: {error.code}\n")
    
    if error.file and error.line:
        prompt_parts.append(f"File: {error.file}, Line: {error.line}\n")
    
    prompt_parts.append(f"\nError message:\n{error.message}\n\n")
    
    prompt_parts.extend([
        "Please provide the corrected code. Make sure your solution:",
        "1. Fixes the specific error mentioned",
        "2. Maintains the original functionality",
        "3. Follows Rust best practices"
    ])
    
    return "\n".join(prompt_parts)
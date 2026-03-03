import os
import time
import re
from typing import Set, Dict, Optional, List
from utils import ErrorInfo, Completion, parse_cargo_error, read_file, write_file, run_command


class RustProject:
    """Rust项目管理类"""
    def __init__(self, root_path: str):
        self.root_path = root_path
        self.max_attempts = 10
        self.max_time = 600  # 10分钟
        self.start_time = time.time()
        self.attempts = 0
        # 保存补丁文件的目录
        self.patch_dir = os.path.join(self.root_path, 'patches')
        # 确保补丁目录存在
        os.makedirs(self.patch_dir, exist_ok=True)

    def check(self) -> Set[ErrorInfo]:
        """检查项目中的错误"""
        try:
            # 运行 cargo check 命令，使用更详细的输出格式
            # 先尝试不带json格式的输出，以便更好地捕获实际错误
            print("[DEBUG] Running cargo check...")
            result = run_command(
                ["cargo", "check"],  # 不使用json格式，获取更详细的错误信息
                cwd=self.root_path
            )

            # 合并stdout和stderr，因为cargo可能将错误输出到stdout
            combined_output = result.stdout + "\n" + result.stderr
            print(f"[DEBUG] Cargo check combined output length: {len(combined_output)} chars")

            # 解析错误
            errors_list = parse_cargo_error(combined_output)
            return set(errors_list)
        except Exception as e:
            print(f"Error running cargo check: {e}")
            return set()

    def create_snapshot(self) -> Dict[str, str]:
        """创建项目快照"""
        snapshot = {}
        for root, _, files in os.walk(self.root_path):
            # 跳过 target 目录
            if 'target' in root.split(os.sep):
                continue
            
            for file in files:
                file_path = os.path.join(root, file)
                # 获取相对路径作为键
                rel_path = os.path.relpath(file_path, self.root_path)
                content = read_file(file_path)
                if content is not None:
                    snapshot[rel_path] = content
        return snapshot

    def restore_snapshot(self, snapshot: Dict[str, str]):
        """恢复项目快照"""
        # 清除当前项目文件（保留目录结构）
        for root, _, files in os.walk(self.root_path):
            # 跳过 target 目录和 patches 目录
            path_parts = root.split(os.sep)
            if 'target' in path_parts or 'patches' in path_parts:
                continue
            
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Error removing file {file_path}: {e}")
        
        # 恢复快照中的文件
        for rel_path, content in snapshot.items():
            file_path = os.path.join(self.root_path, rel_path)
            write_file(file_path, content)

    def apply_patch(self, completion: Completion) -> bool:
        """
        应用补丁到文件
        
        Args:
            completion: 从ChangeLog格式解析出的补全信息
            
        Returns:
            布尔值，表示补丁是否成功应用
        """
        file_path = os.path.join(self.root_path, completion.file_path)
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return False

        try:
            # 读取文件内容
            content = read_file(file_path)
            if content is None:
                print(f"Failed to read file: {file_path}")
                return False
            
            # 解析文件内容为行列表
            lines = content.split('\n')
            
            # 验证行范围
            start_idx = completion.line_start - 1  # 转换为0索引
            end_idx = completion.line_end
            
            # 确保行范围有效
            if start_idx < 0 or end_idx > len(lines):
                print(f"Invalid line range: {start_idx+1}-{end_idx} (file has {len(lines)} lines)")
                return False
            
            # 处理补丁内容，移除行号前缀并保留缩进
            processed_lines = []
            
            for line in completion.content.split('\n'):
                # 处理空行
                if not line.strip():
                    processed_lines.append('')
                    continue
                
                # 处理带有行号前缀的行（格式如: [12] content）
                if line.strip().startswith('[') and ']' in line.strip():
                    # 提取缩进
                    indent_match = re.match(r'(\s*)', line)
                    indent = indent_match.group(1) if indent_match else ''
                    
                    # 提取行内容（去掉行号前缀）
                    line_content = line.split(']', 1)[1].strip()
                    
                    # 保留原有的缩进并添加处理后的内容
                    processed_lines.append(f"{indent}{line_content}")
                else:
                    # 对于没有行号前缀的行，直接使用
                    processed_lines.append(line)
            
            # 应用补丁
            lines[start_idx:end_idx] = processed_lines
            
            # 保存补丁到单独的文件
            return self.save_patch(completion, processed_lines)
        except Exception as e:
            print(f"Error applying patch: {e}")
            return False
    
    def save_patch(self, completion: Completion, processed_lines: List[str]) -> bool:
        """将补丁保存为单独的文件"""
        try:
            # 确保patches目录存在
            patch_dir = os.path.join(self.root_path, 'patches')
            os.makedirs(patch_dir, exist_ok=True)
            
            # 生成补丁文件路径
            timestamp = int(time.time())
            base_name = os.path.basename(completion.file_path)
            patch_filename = f"patch_{base_name}_{timestamp}.patch"
            patch_path = os.path.join(patch_dir, patch_filename)
            
            # 构建补丁内容
            patch_content = "# RustAssistant Patch\n"
            patch_content += f"# File: {completion.file_path}\n"
            patch_content += f"# Lines: {completion.line_start}-{completion.line_end}\n"
            patch_content += f"# Timestamp: {timestamp}\n\n"
            patch_content += "--- FIX\n"
            patch_content += completion.content + "\n"
            
            # 写入文件
            with open(patch_path, 'w', encoding='utf-8') as f:
                f.write(patch_content)
            
            return True
            
        except Exception:
            return False



    def should_giveup(self) -> bool:
        """判断是否应该放弃"""
        # 不再自动增加attempts计数，由调用方控制
        elapsed_time = time.time() - self.start_time
        return self.attempts >= self.max_attempts or elapsed_time >= self.max_time
    
    def increment_attempts(self):
        """增加尝试次数"""
        self.attempts += 1
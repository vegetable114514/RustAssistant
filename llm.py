import os
import re
import json
import requests
from typing import List, Optional, Dict, Any
from utils import Completion, ErrorInfo, format_prompt


class LLMClient:
    """LLM客户端类"""
    def __init__(self, model: str, api_key: str, base_url: Optional[str] = None):
        self.model = model
        self.api_key = api_key
        # 如果未提供base_url，使用默认的OpenAI API URL
        self.base_url = base_url or "https://api.openai.com/v1/chat/completions"

    def invoke(self, prompt: str, n: int = 1) -> List[Completion]:
        """调用真实LLM生成补全
        
        Args:
            prompt: 输入提示
            n: 需要生成的补全数量
            
        Returns:
            生成的补全列表
        """
        # 直接调用真实API
        print(f"[INFO] 正在调用真实LLM API: {self.model}，生成{n}个补全")
        return self._real_invoke(prompt, n)
    
    def _parse_changelog_response(self, response: str) -> tuple:
        """
        解析LLM返回的ChangeLog格式响应
        
        Args:
            response: LLM返回的ChangeLog格式响应
            
        Returns:
            (file_path, line_start, line_end, fixed_code) 元组
        """
        import re
        
        # 提取文件路径
        file_match = re.search(r'ChangeLog:\d+@([^\n]+)', response)
        file_path = file_match.group(1) if file_match else "src/main.rs"
        
        # 提取FixedCode部分
        fixed_code_match = re.search(r'FixedCode@(\d+)-(\d+):\n([\s\S]+?)(?=OriginalCode|ChangeLog|$|---)', response)
        if fixed_code_match:
            line_start = int(fixed_code_match.group(1))
            line_end = int(fixed_code_match.group(2))
            
            # 提取修复后的代码，保留原始缩进并移除行号前缀
            fixed_code_content = fixed_code_match.group(3).strip()
            code_lines = []
            
            for line in fixed_code_content.split('\n'):
                line_stripped = line.strip()
                if line_stripped.startswith('[') and ']' in line_stripped:
                    # 提取缩进部分
                    indent_match = re.match(r'(\s*)', line)
                    indent = indent_match.group(1) if indent_match else ''
                    
                    # 提取行号后的代码内容
                    content_part = line_stripped.split(']', 1)[1].strip()
                    code_lines.append(f"{indent}{content_part}")
                elif line_stripped:
                    # 对于没有行号前缀的有效行，保留原始格式
                    code_lines.append(line)
            
            # 合并为最终代码
            fixed_code = '\n'.join(code_lines)
        else:
            # 默认值
            line_start = 1
            line_end = 5
            fixed_code = "// No valid fixed code found in ChangeLog response"
        
        return file_path, line_start, line_end, fixed_code



    def _real_invoke(self, prompt: str, n: int) -> List[Completion]:
        """真实调用LLM API
        
        注意：这是一个示例实现，实际使用时需要根据具体的API文档进行调整
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "n": n,
            "temperature": 0.7
        }
        
        # 确保URL包含正确的API端点路径
        # 处理可能已经包含endpoint的情况
        base_url = self.base_url.rstrip('/')
        endpoint = "/chat/completions"
        
        # 如果base_url已经以endpoint结尾，则直接使用
        if base_url.endswith(endpoint):
            url = base_url
        else:
            url = base_url + endpoint
        
        print(f"[DEBUG] 调用API URL: {url}")
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code != 200:
            raise Exception(f"API request failed: {response.status_code} {response.text}")
        
        response_data = response.json()
        completions = []
        
        for choice in response_data.get("choices", []):
            message = choice.get("message", {}).get("content", "")
            # 简单提取置信度（实际API可能没有这个字段）
            confidence = 1.0 - (choice.get("index", 0) * 0.1)
            
            completion = Completion(
                content=message.strip(),
                confidence=confidence,
                file_path="src/main.rs",  # 默认文件路径，实际使用时需要从提示或响应中提取
                line_start=1,  # 默认起始行，实际使用时需要从提示或响应中提取
                line_end=5     # 默认结束行，实际使用时需要从提示或响应中提取
            )
            completions.append(completion)
        
        return completions


def get_best_completion(completions: List[Completion]) -> Optional[Completion]:
    """选择最佳补全
    
    Args:
        completions: 补全列表
        
    Returns:
        最佳补全，如果列表为空则返回None
    """
    if not completions:
        return None
    
    # 简单实现：选择confidence最高的补全
    return max(completions, key=lambda x: x.confidence)


def instantiate_prompt(error: ErrorInfo, project_path: str = "") -> str:
    """
    根据错误信息实例化提示
    使用RUSTASSISTANT prompt模板格式（Fig.4）
    """
    cmd = "cargo check"
    error_info = error.message
    
    # 如果有错误代码，添加到错误信息中
    if error.code:
        error_info += f" (error code: {error.code})"
    
    # 获取错误解释（这里简单实现，实际可能需要更复杂的分析）
    error_explanation = ""
    
    # 获取代码片段
    code_snippets = ""
    if error.file and error.line:
        # 构建完整的文件路径
        full_file_path = error.file
        if project_path and not os.path.isabs(full_file_path):
            full_file_path = os.path.join(project_path, full_file_path)
        
        # 尝试读取文件内容
        try:
            with open(full_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 获取错误行前后的代码（上下文）
            start_line = max(1, error.line - 5)
            end_line = min(len(lines) + 1, error.line + 5)
            
            snippet_lines = []
            for i in range(start_line, end_line):
                line_num = i
                code_line = lines[i-1].rstrip('\n')  # i-1因为lines是0索引
                snippet_lines.append(f"[{line_num}] {code_line}")
            
            code_snippets = "\n".join(snippet_lines)
        except Exception:
            # 如果无法读取文件，使用占位符
            code_snippets = f"[代码片段不可用: {error.file}:{error.line}]"
    
    # 构建完整的prompt
    prompt = f"""RUSTASSISTANT prompt template preamble 
 You are given the below error from running '{cmd}' and 
 related Rust code snippets. 
 Prompt context with error information and code snippets 
 {error_info} {error_explanation}
 --- 
 {code_snippets}
 Instructions for fixing the error 
 Instructions: Fix the error on the above code snippets. 
 Not every snippet might require a fix or be relevant to 
 the error, but take into account the code in all above 
 snippets as it could help you derive the best possible 
 fix. Assume that the snippets might not be complete and 
 could be missing lines above or below. Do not add comments 
 or code that is not necessary to fix the error. Do not 
 use unsafe or unstable features (through '#![feature(... 
 ]'). For your answer, return one or more ChangeLog groups, 
 each containing one or more fixes to the above code 
 snippets. Each group must be formatted with the below 
 instructions. 
 Instructions and examples for formatting the changelog output 
 Format instructions: Each ChangeLog group must start with 
 a description of its included fixes. The group must then 
 list one or more pairs of (OriginalCode, FixedCode) code 
 snippets. Each OriginalCode snippet must list all 
 consecutive original lines of code that must be replaced 
 (including a few lines before and after the fixes), 
 followed by the FixedCode snippet with all consecutive 
 fixed lines of code that must replace the original lines 
 of code (including the same few lines before and after 
 the changes). In each pair, the OriginalCode and FixedCode 
 snippets must start at the same source code line number N. 
 Each listed code line, in both the OriginalCode and 
 FixedCode snippets, must be prefixed with [N] that matches 
 the line index N in the above snippets, and then be 
 prefixed with exactly the same whitespace indentation as 
 the original snippets above. 
 --- 
 ChangeLog:1@<file> 
 FixDescription: <summary>. 
 OriginalCode@4-6: 
 [4] <white space> <original code line> 
 [5] <white space> <original code line> 
 [6] <white space> <original code line> 
 FixedCode@4-6: 
 [4] <white space> <fixed code line> 
 [5] <white space> <fixed code line> 
 [6] <white space> <fixed code line> 
 OriginalCode@9-10: 
 [9] <white space> <original code line> 
 [10] <white space> <original code line> 
 FixedCode@9-9: 
 [9] <white space> <fixed code line> 
 ... 
 ChangeLog:K@<file> 
 FixDescription: <summary>. 
 OriginalCode@15-16: 
 [15] <white space> <original code line> 
 [16] <white space> <original code line> 
 FixedCode@15-17: 
 [15] <white space> <fixed code line> 
 [16] <white space> <fixed code line> 
 [17] <white space> <fixed code line> 
 --- 
 Answer:
"""
    
    return prompt
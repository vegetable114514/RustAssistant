from typing import Set, Dict, Optional
from utils import ErrorInfo, Completion
from project import RustProject
from llm import LLMClient, instantiate_prompt, get_best_completion


def choose_any(errors: Set[ErrorInfo]) -> ErrorInfo:
    """从错误集合中选择任意一个错误
    
    Args:
        errors: 错误集合
        
    Returns:
        选择的错误
    """
    # 在Python中，集合是无序的，pop()会移除并返回任意元素
    # 使用copy()避免修改原始集合
    return next(iter(errors.copy()))


def get_error_identifier(e: ErrorInfo) -> str:
    """获取错误的唯一标识符，用于错误比较
    
    根据算法描述，错误表示为：错误码 + 错误消息 + 文件名
    不包含行号信息
    
    Args:
        e: 错误信息
        
    Returns:
        错误的唯一标识符
    """
    return f"{e.code or ''}:{e.message}:{e.file}"


def rust_assistant(m: LLMClient, n: int, project: RustProject) -> bool:
    """
    RustAssistant算法实现
    
    根据算法框架实现，包含错误组管理、LLM调用和修复逻辑
    
    Args:
        m: LLM客户端
        n: 补全数量
        project: Rust项目
        
    Returns:
        是否成功修复所有错误
    """
    print("=== Starting RustAssistant algorithm ===")
    
    # 步骤1: 检查项目错误
    errs = project.check()
    print(f"Initial errors found: {len(errs)}")
    
    # 已放弃的错误集合（使用错误标识符）
    given_up_errors = set()
    
    # 步骤2: 当错误集不为空时循环
    max_outer_iterations = len(errs)  # 外循环最多执行初始错误数量次
    iteration = 0
    
    while errs and iteration < max_outer_iterations:
        iteration += 1
        project.increment_attempts()  # 增加尝试次数
        print(f"\n=== Iteration {iteration}/{max_outer_iterations}: Processing {len(errs)} errors ===")
        
        # 步骤3: 选择任意错误
        e = choose_any(errs)
        error_msg = e.message[:100] + '...' if len(e.message) > 100 else e.message
        print(f"Selected error: {e.code or 'Unknown'} - {error_msg}")
        print(f"Error location: {e.file}:{e.line}")
        
        # 检查是否已经放弃过这个错误
        error_id = get_error_identifier(e)
        if error_id in given_up_errors:
            print(f"  Skipping error that was previously given up")
            # 从错误集合中移除
            errs.remove(e)
            continue
        
        # 步骤4: 初始化错误组，包含当前错误
        g = {e}
        
        # 步骤5: 创建项目快照
        snap = project.create_snapshot()
        if snap:
            print(f"Created project snapshot successfully")
        else:
            print("Warning: Failed to create project snapshot")
        
        # 内部循环状态管理
        seen_errors = set()  # 跟踪错误组中出现过的所有唯一错误
        previous_error_group = None  # 上一次迭代的错误组
        inner_iteration = 0
        max_unique_errors = 100  # 错误组生命周期内的最大唯一错误数
        
        print(f"[DEBUG] Starting inner loop with error group size: {len(g)}")
        
        # 步骤6: 当错误组不为空时循环
        while g:
            inner_iteration += 1
            print(f"  Inner iteration {inner_iteration}: Processing {len(g)} errors in error group")
            print(f"[DEBUG] Error details: {[f'{e.code}:{e.message[:50]}' for e in g]}")
            
            # 检查放弃条件1: 错误组生命周期内的唯一错误数超过限制
            for error in g:
                seen_errors.add(get_error_identifier(error))
            
            if len(seen_errors) >= max_unique_errors:
                print(f"  Giving up: Maximum unique errors ({max_unique_errors}) reached in error group")
                given_up_errors.add(error_id)
                project.restore_snapshot(snap)
                break
            
            # 检查放弃条件2: 错误组没有变化（无进展）
            if previous_error_group and previous_error_group == g:
                print(f"  Giving up: No progress in error group")
                given_up_errors.add(error_id)
                project.restore_snapshot(snap)
                break
            
            # 保存当前错误组用于下次比较
            previous_error_group = g.copy()
            
            # 步骤7: 选择错误组中的任意错误
            e_prime = choose_any(g)
            
            # 步骤8: 实例化提示
            try:
                p = instantiate_prompt(e_prime, project.root_path)
                print(f"  Generated prompt for error")
            except Exception as e:
                print(f"  Error generating prompt: {e}")
                given_up_errors.add(error_id)
                project.restore_snapshot(snap)
                break
            
            # 调用LLM获取补全
            try:
                # 注意：传递n参数以生成指定数量的候选修复方案
                n_completions = m.invoke(p, n)
                print(f"  Received {len(n_completions)} completions from LLM")
            except Exception as e:
                print(f"  Error invoking LLM: {e}")
                given_up_errors.add(error_id)
                project.restore_snapshot(snap)
                break
            
            # 步骤10: 选择最佳补全
            c = get_best_completion(n_completions)
            if not c:
                print("  No valid completion found")
                given_up_errors.add(error_id)
                project.restore_snapshot(snap)
                break
            
            print(f"  Selected best completion with confidence: {c.confidence:.2f}")
            print(f"  Patch location: {c.file_path}:{c.line_start}-{c.line_end}")
            
            # 步骤11: 保存补丁为单独文件
            import os
            project_abs_path = os.path.abspath(project.root_path)
            
            # 提前创建补丁目录
            patch_dir_abs = os.path.abspath(os.path.join(project_abs_path, 'patches'))
            os.makedirs(patch_dir_abs, exist_ok=True)
            
            # 准备processed_lines参数
            file_full_path = os.path.join(project_abs_path, c.file_path)
            processed_lines = []
            try:
                if os.path.exists(file_full_path):
                    with open(file_full_path, 'r', encoding='utf-8') as f:
                        processed_lines = f.readlines()
                # 始终确保有内容用于补丁
                if not processed_lines:
                    processed_lines = c.content.split('\n')
            except Exception:
                # 发生错误时使用completion内容作为备选
                processed_lines = c.content.split('\n')
            
            # 调用save_patch方法
            success = project.save_patch(c, processed_lines)
            
            print(f"  Saved patch for {c.file_path}")
            
            # 对于保存补丁模式，我们不直接修改文件，所以不需要更新快照
            # 为了继续处理下一个错误，我们仍然需要检查当前错误状态
            current_errors = project.check()
            
            # 更新错误组
            g = current_errors
            
            print(f"  Updated error group size: {len(g)}")
            
            # 检查是否应该放弃（其他条件）
            if project.should_giveup():
                print("  Giving up: Project reached maximum attempts or time limit")
                given_up_errors.add(error_id)
                # 对于保存补丁模式，不需要恢复快照，因为我们没有修改文件
                break
        
        # 步骤18: 更新错误集合（注意：我们只是保存补丁，没有实际修复错误）
        errs = project.check()
        print(f"  Current error count: {len(errs)}")
        print(f"  Patches have been saved to {project.patch_dir} directory")
    
    # 注意：在补丁保存模式下，我们只保存了补丁文件，没有实际修复错误
    print(f"\n🎉 RustAssistant process completed successfully!")
    print(f"  {len(errs)} potential fixes have been saved as patch files.")
    print(f"  You can review and apply these patches manually from the {project.patch_dir} directory.")
    success = True
    
    print("=== RustAssistant algorithm completed ===")
    return success
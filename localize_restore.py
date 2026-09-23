#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Command Code 还原脚本（英文文件名版本）
一键将 Command Code 桌面应用还原为英文原版
"""

import os
import sys
import subprocess
from pathlib import Path

def _shortcut_app_dir():
    """从开始菜单快捷方式反推安装目录（兼容用户目录重定向到 D 盘等情况）。"""
    try:
        import glob
        lnk_paths = []
        if os.environ.get('APPDATA'):
            lnk_paths.append(os.path.join(os.environ.get('APPDATA'), 'Microsoft', 'Windows',
                                           'Start Menu', 'Programs', 'Command Code.lnk'))
        username = os.environ.get('USERNAME', '')
        for drive in ['C', 'D', 'E', 'F', 'G', 'H']:
            if username:
                lnk_paths.append(os.path.join(f'{drive}:\\', 'Users', username, 'AppData', 'Roaming',
                                              'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Command Code.lnk'))
            lnk_paths.append(os.path.join(f'{drive}:\\', 'ProgramData', 'Microsoft', 'Windows',
                                          'Start Menu', 'Programs', 'Command Code.lnk'))
        for lnk in lnk_paths:
            if not lnk or not os.path.exists(lnk):
                continue
            try:
                with open(lnk, 'rb') as f:
                    data = f.read()
                for enc in ('utf-16-le', 'mbcs'):
                    try:
                        text = data.decode(enc, errors='ignore')
                    except Exception:
                        continue
                    idx = text.find('Command Code.exe')
                    if idx != -1:
                        start = max(text.rfind(d + ':\\', 0, idx) for d in 'CDEFGH')
                        if start != -1:
                            exe = text[start:idx + len('Command Code.exe')]
                            exe = ''.join(ch for ch in exe if 31 < ord(ch) < 127 or ch in '\\:. _-()')
                            app_dir = os.path.dirname(exe.strip().strip('\x00'))
                            if os.path.exists(os.path.join(app_dir, 'resources', 'app', 'out', 'main', 'index.js')):
                                return app_dir
            except Exception:
                continue
    except Exception:
        pass
    return None


def find_app_dir():
    """查找 Command Code 安装目录"""
    # 优先环境变量
    if os.environ.get('CC_APP_DIR'):
        return os.environ.get('CC_APP_DIR')

    # 常见安装位置
    candidates = []

    if os.environ.get('LOCALAPPDATA'):
        candidates.append(os.path.join(os.environ.get('LOCALAPPDATA'), 'Programs', 'Command Code'))
    if os.environ.get('PROGRAMFILES'):
        candidates.append(os.path.join(os.environ.get('PROGRAMFILES'), 'Command Code'))
    if os.environ.get('PROGRAMFILES(X86)'):
        candidates.append(os.path.join(os.environ.get('PROGRAMFILES(X86)'), 'Command Code'))

    # 用户目录被重定向到其它盘（如 D:\Users\<name>）时的补充候选
    username = os.environ.get('USERNAME', '')
    if username:
        for drive in ['C', 'D', 'E', 'F', 'G', 'H']:
            candidates.append(os.path.join(f'{drive}:\\', 'Users', username, 'AppData', 'Local', 'Programs', 'Command Code'))

    # 常见自定义安装位置
    for drive in ['D', 'C', 'E', 'F', 'G', 'H']:
        candidates.append(os.path.join(f'{drive}:\\', 'commandcodedesktop', 'Command Code'))

    for candidate in candidates:
        if os.path.exists(os.path.join(candidate, 'resources', 'app', 'out', 'main', 'index.js')):
            return candidate

    return _shortcut_app_dir()

def main():
    print("=" * 43)
    print("  Command Code Restore English Version")
    print("=" * 43)
    print()
    
    # 支持命令行参数
    if len(sys.argv) > 1:
        app_dir = sys.argv[1]
    else:
        # 查找安装目录
        app_dir = find_app_dir()
    
    if not app_dir:
        print("[Tip] Command Code installation directory not found automatically.")
        print("Please specify installation directory using one of these methods:")
        print("  1. Set environment variable: set CC_APP_DIR=D:\\Your\\Path\\Command Code")
        print("  2. Command line parameter: python localize_restore.py \"D:\\Your\\Path\\Command Code\"")
        print("  3. Direct run: python localize.py restore \"D:\\Your\\Path\\Command Code\"")
        sys.exit(1)
    
    if not os.path.exists(os.path.join(app_dir, 'resources', 'app', 'out', 'main', 'index.js')):
        print(f"[Error] Command Code application not found in directory: {app_dir}")
        sys.exit(1)
    
    print(f"Installation directory: {app_dir}")
    print()
    
    # 执行还原
    script_dir = os.path.dirname(os.path.abspath(__file__))
    localize_script = os.path.join(script_dir, 'localize.py')
    
    try:
        result = subprocess.run([sys.executable, localize_script, 'restore', app_dir], 
                              capture_output=True, text=True, errors='replace')
        
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        
        if result.returncode == 2:
            # localize.py 用 exit 2 表示“已是目标状态”（已汉化/无需重复操作），不视为失败
            sys.exit(0)

        if result.returncode != 0:
            print()
            print("[Failed] Restore not completed. You can manually run for details:")
            print(f'  python "{localize_script}" restore "{app_dir}"')
            sys.exit(1)
        
        print()
        print("[Done] Restored to English version.")
        
    except Exception as e:
        print(f"[Error] Error during restore: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

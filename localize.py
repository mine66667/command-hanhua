#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Command Code 桌面版 一键汉化器（核心逻辑，Python 实现）
# 用法:
#   python localize.py apply    [安装目录]   应用词典汉化（先自动备份）
#   python localize.py restore  [安装目录]   从最近备份还原
#   python localize.py status   [安装目录]   查看汉化/备份状态
#   python localize.py dry      [安装目录]   试运行，只报告将替换多少处
#
# 安装目录解析优先级（后两者为空/失败时依次回退）:
#   1. 命令行参数: python localize.py apply "D:\path\to\Command Code"
#   2. 环境变量:   set CC_APP_DIR=D:\path\to\Command Code
#   3. 自动探测:   遍历常见安装位置（Program Files、AppData、D:\commandcodedesktop 等），
#                  匹配含 resources\app\out\main\index.js 特征的目录
#   4. 显式报错并提示传入路径

import os
import sys
import json
import shutil
import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Set

# 常见安装位置候选（按平台）。命中条件为存在 Command Code 的 Electron 应用特征文件。
def _shortcut_app_dir() -> Optional[str]:
    """从开始菜单快捷方式解析安装目录（兼容用户目录重定向到 D 盘等情况）。"""
    try:
        import glob as _glob
        lnk_paths = _glob.glob(os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Command Code.lnk'))
        # 用户目录可能被重定向到其它盘（如 D:\Users\<name>），逐盘补充扫描
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
                import struct
                with open(lnk, 'rb') as f:
                    data = f.read()
                # 快捷方式内嵌目标路径为明文 UTF-16LE/ANSI，简单搜索 "...\Command Code\Command Code.exe"
                for enc in ('utf-16-le', 'mbcs'):
                    try:
                        text = data.decode(enc, errors='ignore')
                    except Exception:
                        continue
                    idx = text.find('Command Code.exe')
                    if idx != -1:
                        # 向前取整段路径（含盘符）
                        start = max(text.rfind(drive + ':\\', 0, idx) for drive in 'CDEFGH')
                        if start != -1:
                            exe = text[start:idx + len('Command Code.exe')]
                            exe = ''.join(ch for ch in exe if 31 < ord(ch) < 127 or ch in '\\:. _-()')
                            app_dir = os.path.dirname(exe.strip().strip('\x00'))
                            if os.path.exists(os.path.join(app_dir, 'resources', 'app', 'out', 'main', 'index.js')):
                                return app_dir
                    # 兼容部分 lnk 只存目录 "...\Command Code"
                    idx2 = text.find('Command Code')
                    if idx2 != -1:
                        start = max(text.rfind(drive + ':\\', 0, idx2) for drive in 'CDEFGH')
                        if start != -1:
                            app_dir = text[start:idx2 + len('Command Code')]
                            app_dir = ''.join(ch for ch in app_dir if 31 < ord(ch) < 127 or ch in '\\:. _-()').strip().strip('\x00')
                            if os.path.exists(os.path.join(app_dir, 'resources', 'app', 'out', 'main', 'index.js')):
                                return app_dir
            except Exception:
                continue
    except Exception:
        pass
    return None


def detect_app_dir() -> Optional[str]:
    candidates = []

    # 环境变量（最高优先）
    if os.environ.get('CC_APP_DIR'):
        candidates.append(os.environ.get('CC_APP_DIR'))

    # Windows 标准位置
    if os.environ.get('LOCALAPPDATA'):
        candidates.append(os.path.join(os.environ.get('LOCALAPPDATA'), 'Programs', 'Command Code'))
    if os.environ.get('PROGRAMFILES'):
        candidates.append(os.path.join(os.environ.get('PROGRAMFILES'), 'Command Code'))
    if os.environ.get('PROGRAMFILES(X86)'):
        candidates.append(os.path.join(os.environ.get('PROGRAMFILES(X86)'), 'Command Code'))
    if os.environ.get('APPDATA'):
        candidates.append(os.path.join(os.environ.get('APPDATA'), 'Command Code'))

    # 用户目录被重定向到其它盘（如 D:\Users\<name>）时的补充候选
    username = os.environ.get('USERNAME', '')
    if username:
        for drive in ['C', 'D', 'E', 'F', 'G', 'H']:
            candidates.append(os.path.join(f'{drive}:\\', 'Users', username, 'AppData', 'Local', 'Programs', 'Command Code'))

    # macOS
    if sys.platform == 'darwin':
        candidates.append('/Applications/Command Code.app/Contents/Resources/app')

    # Linux
    if sys.platform == 'linux':
        candidates.append('/opt/Command Code')

    # Windows 常见自定义安装盘
    for drive in ['C', 'D', 'E', 'F', 'G', 'H']:
        candidates.append(os.path.join(f'{drive}:\\', 'commandcodedesktop', 'Command Code'))

    for candidate in candidates:
        if not candidate:
            continue
        try:
            if os.path.exists(os.path.join(candidate, 'resources', 'app', 'out', 'main', 'index.js')):
                return candidate
        except Exception:
            pass

    # 最后尝试从开始菜单快捷方式反推（覆盖注册表/重定向等边缘情况）
    return _shortcut_app_dir()

# 全局变量
APP_DIR = None
OUT_DIR = None
BACKUP_ROOT = None
DICT_PATH = None
APP_RES_ROOT = None

def init_globals():
    global APP_DIR, OUT_DIR, BACKUP_ROOT, DICT_PATH, APP_RES_ROOT
    
    # 获取安装目录：用法 python localize.py <apply|restore|status|dry> [安装目录]
    if len(sys.argv) > 2 and sys.argv[2] and not sys.argv[2].startswith('-'):
        APP_DIR = sys.argv[2]
    else:
        APP_DIR = detect_app_dir()
    
    if not APP_DIR:
        return False
    
    OUT_DIR = os.path.join(APP_DIR, 'resources', 'app', 'out')
    BACKUP_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
    DICT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dict.json')
    APP_RES_ROOT = os.path.join(APP_DIR, 'resources', 'app')
    
    return True

# 目标文件: 应用自有 UI 的 renderer chunk + main + harness 配置 schema。
# 白名单前缀(排除语法高亮/图表/数学等第三方库 chunk):
#   index-* (主 bundle, 但 index-Bxgrt3DT/mermaid、index-DqxT88dM/shiki 等库会被内容特征排除)
#   workspace-screen-* settings-panel-* terminal-* source-panel-*
#   auth-screen-* onboarding-screen-* browser-panel-*
# main/index.js 恒为应用主进程。
# harness/dist/index.js: Config 设置页文本源(label/description schema)。
UI_CHUNK_RE = re.compile(r'^(workspace-screen|settings-panel|terminal-|source-panel|auth-screen|onboarding-screen|browser-panel)')

# assets 下同 UI 前缀的最新文件（升级后旧 chunk 残留时只取当前版本）
def newest_by_prefix(assets_dir: str) -> List[str]:
    prefixes = ['workspace-screen', 'settings-panel', 'browser-panel', 'source-panel',
                'auth-screen', 'onboarding-screen', 'terminal', 'index']
    by_prefix = {}
    
    try:
        files = os.listdir(assets_dir)
    except:
        return []
    
    for prefix in prefixes:
        best = None
        for f in files:
            if not (f.startswith(prefix + '-') or f.startswith(prefix + '.')):
                continue
            if not f.endswith('.js'):
                continue
            
            full = os.path.join(assets_dir, f)
            stat = os.stat(full)
            if best is None or stat.st_mtime > best['mtime']:
                best = {'file': full, 'mtime': stat.st_mtime}
        
        if best:
            by_prefix[prefix] = best['file']
    
    return list(by_prefix.values())

def target_files() -> List[str]:
    files = []
    assets = os.path.join(OUT_DIR, 'renderer', 'assets')
    
    if os.path.exists(assets):
        # 1) 每个 UI 前缀只取最新文件（避免旧版残留干扰）
        for f in newest_by_prefix(assets):
            base = os.path.basename(f)
            if UI_CHUNK_RE.match(base):
                files.append(f)
                continue
            
            # index-* 主入口: 只收录真正含应用 UI 的(体积>700KB 且非语言/图表库)
            if base.startswith('index-'):
                with open(f, 'r', encoding='utf-8') as file:
                    code = file.read()
                stat = os.stat(f)
                if stat.st_size > 700 * 1024 and not re.search(r'mermaid|shiki|textmate|oniguruma', code[:500], re.IGNORECASE):
                    files.append(f)
    
    main = os.path.join(OUT_DIR, 'main', 'index.js')
    if os.path.exists(main):
        files.append(main)
    
    # harness 包: Config 设置页 schema 文本源
    harness = os.path.join(APP_DIR, 'resources', 'app', 'node_modules', '@commandcode', 'harness', 'dist', 'index.js')
    if os.path.exists(harness):
        files.append(harness)
    
    return files

# 计算目标文件相对 resources/app 的路径(用于备份目录)
def rel_path(f: str) -> str:
    rel = os.path.relpath(f, APP_RES_ROOT)
    if rel.startswith('..'):
        return os.path.basename(f)
    return rel

def dict_terms() -> List[Dict[str, str]]:
    with open(DICT_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['terms']

def is_chinese_app() -> bool:
    # 统计简体中文 UI 特征。仅统计 CJK 片段会误伤 zod 等库的日文 locale 数据
    # （日文假名在 U+3040–30FF 区，但日文汉字与中文同区）。这里要求片段含
    # 简体中文高频用字（的/了/是/在/与/这/进/请 等），或片段总量显著超过
    # 日文 locale 规模（zod 日文约 200 段，但整文件中文会轻松上千段）。
    for f in target_files():
        try:
            with open(f, 'r', encoding='utf-8') as file:
                s = file.read()
            
            runs = len(re.findall(r'[\u4e00-\u9fff]{2,}', s))
            if runs > 200:
                # 简体特征字（日文 locale 几乎不含这些简体字）
                zh_count = len(re.findall(r'[的了是在与进这请会话文件设置打开发送取消确认删除保存新增管理需要可以内容模式工具命令]', s))
                # 日文假名（zod ja locale 的特征）
                ja_count = len(re.findall(r'[\u3040-\u30ff]', s))
                # 简体字多且假名少 → 真汉化；假名多 → 日语 locale（如 zod ja/zh-TW 变体）
                if zh_count > 100 and ja_count < zh_count:
                    return True
        except:
            pass
    return False

def find_backups() -> List[str]:
    if not os.path.exists(BACKUP_ROOT):
        return []
    
    backups = [d for d in os.listdir(BACKUP_ROOT) if d.startswith('backup-')]
    backups.sort(reverse=True)
    return backups

def backup_dir_name() -> str:
    ts = datetime.now().isoformat().replace(':', '-').replace('.', '-')
    return f'backup-{ts}'

def do_backup() -> str:
    dir_path = os.path.join(BACKUP_ROOT, backup_dir_name())
    os.makedirs(dir_path, exist_ok=True)
    
    for f in target_files():
        rel = rel_path(f)
        dest = os.path.join(dir_path, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(f, dest)
    
    return dir_path

# 扫描 JS 中注释区间(行注释 // 与块注释 /* */)，返回 [start,end] 数组(半开区间)。
# 简易词法: 需跳过字符串/模板串/正则字面量内的 // 与 /*，避免误判。
# 正则识别用启发式: / 前一个有效字符为 ( , = : [ ! & | ? { } ; 等(或行首)则视为正则。
def scan_comments(code: str) -> List[Tuple[int, int]]:
    ranges = []
    n = len(code)
    i = 0
    state = 'code'  # code | line | block | str | tpl | regex
    str_quote = ''
    start = 0
    
    def is_regex_start(pos: int) -> bool:
        j = pos - 1
        while j >= 0 and code[j].isspace():
            j -= 1
        if j < 0:
            return True
        c = code[j]
        return c in '([{:;,=!?&|+-*%^~<>'
    
    while i < n:
        c = code[i]
        nx = code[i + 1] if i + 1 < n else ''
        
        if state == 'code':
            # // 行注释(排除协议:// )
            if c == '/' and nx == '/' and (i == 0 or code[i - 1] != ':'):
                state = 'line'
                start = i
                i += 2
                continue
            if c == '/' and nx == '*':
                state = 'block'
                start = i
                i += 2
                continue
            if c == '/' and is_regex_start(i):
                state = 'regex'
                i += 1
                continue
            if c == '"' or c == "'":
                state = 'str'
                str_quote = c
                i += 1
                continue
            if c == '`':
                state = 'tpl'
                i += 1
                continue
            i += 1
        elif state == 'line':
            if c == '\n':
                ranges.append((start, i))
                state = 'code'
            i += 1
        elif state == 'block':
            if c == '*' and nx == '/':
                ranges.append((start, i + 2))
                state = 'code'
                i += 2
                continue
            i += 1
        elif state == 'str':
            if c == '\\':
                i += 2
                continue
            if c == str_quote:
                state = 'code'
            i += 1
        elif state == 'regex':
            if c == '\\':
                i += 2
                continue
            if c == '/':
                state = 'code'  # 正则结束(忽略 flags)
            elif c == '\n':
                state = 'code'  # 正则含换行不常见, 若跨行则保守结束避免吞代码
            i += 1
        elif state == 'tpl':
            if c == '\\':
                i += 2
                continue
            if c == '`':
                state = 'code'
            i += 1
    
    if state == 'line':
        ranges.append((start, n))
    
    return ranges

def apply_once(dry: bool = False) -> Dict:
    terms = dict_terms()
    files = target_files()
    report = {'files': {}, 'total_replaced': 0, 'applied_terms': 0, 'missed_terms': []}
    
    # 转义正则特殊字符
    def esc(s: str) -> str:
        return re.escape(s)
    
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as file:
                code = file.read()
        except Exception as e:
            print(f'无法读取 {f} {e}')
            continue
        
        replaced = 0
        # 注释区间(基于原 code, 偏移与下方一次大替换的回调 offset 一致)
        comments = scan_comments(code)
        
        def in_comment(pos: int) -> bool:
            for s, e in comments:
                if s <= pos < e:
                    return True
                if pos < s:
                    return False
            return False
        
        # 单次交替正则(按长度降序保证长词条优先), 一次替换保证偏移一致
        sorted_terms = sorted(terms, key=lambda x: len(x['from']), reverse=True)
        applied = {}  # from -> 命中次数
        
        # 构建正则模式
        pattern = '|'.join(esc(t['from']) for t in sorted_terms)
        re_obj = re.compile(pattern)
        
        def replace_func(match):
            nonlocal replaced
            match_text = match.group(0)
            offset = match.start()
            
            # 标识符边界(词条自身两侧) 与 注释跳过
            before = code[offset - 1] if offset > 0 else ''
            after_end = offset + len(match_text)
            after = code[after_end] if after_end < len(code) else ''
            
            if re.search(r'[A-Za-z0-9_$]', before) or re.search(r'[A-Za-z0-9_$]', after):
                return match_text
            if in_comment(offset):
                return match_text
            
            term = next((t for t in sorted_terms if t['from'] == match_text), None)
            if not term:
                return match_text
            
            applied[term['from']] = applied.get(term['from'], 0) + 1
            return term['to']
        
        changed = re_obj.sub(replace_func, code)
        
        for from_term, cnt in applied.items():
            replaced += cnt
            report['applied_terms'] += 1
            base_name = os.path.basename(f)
            if base_name not in report['files']:
                report['files'][base_name] = {'replaced': 0, 'terms': []}
            report['files'][base_name]['replaced'] += cnt
            report['files'][base_name]['terms'].append(from_term)
        
        if changed != code:
            if not dry:
                with open(f, 'w', encoding='utf-8') as file:
                    file.write(changed)
            
            tag = rel_path(f).replace('\\', '/')
            print(f'  {"[试运行] " if dry else ""}{tag}: {replaced} 处')
    
    report['total_replaced'] = sum(v['replaced'] for v in report['files'].values())
    return report

def cmd_apply():
    if is_chinese_app():
        print('检测到目标文件已包含大量中文（可能已汉化）。如需重新汉化请先执行 restore 还原。')
        sys.exit(2)
    
    # 提醒先退出正在运行的应用（中文 Windows 下 tasklist 输出为 GBK，需容错解码）
    if sys.platform == 'win32':
        try:
            result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Command Code.exe', '/FO', 'CSV', '/NH'],
                                    capture_output=True, text=True, encoding='mbcs', errors='ignore')
            if 'Command Code.exe' in result.stdout:
                print('提示: 检测到 Command Code 正在运行。建议先退出应用再汉化，汉化会在重启应用后生效。')
        except Exception:
            pass
    
    print('扫描目标文件…')
    files = target_files()
    print(f'目标文件数: {len(files)}')
    print(f'词典词条数: {len(dict_terms())}')
    
    backup = do_backup()
    print(f'已备份原文件到: {backup}')
    
    report = apply_once(False)
    print(f"\n完成！共替换 {report['total_replaced']} 处，涉及 {report['applied_terms']} 个词条。")
    print('请重启 Command Code 查看效果。如需还原: python localize.py restore')

# 简体字特征计数(用于识别备份里的英文原版/汉化中间态;
# settings 等 chunk 内嵌 zod 中文 locale, 故不设固定阈值, 而同文件比较取最少者)
def zh_feature_count(code: str) -> int:
    return len(re.findall(r'[的了是在与进这请会话文件设置打开发送取消确认删除保存新增管理需要可以内容模式工具命令]', code))

# 在备份目录中定位某目标文件的副本(兼容旧备份的 out 相对布局)
def backup_copy_path(dir_name: str, f: str) -> Optional[str]:
    p1 = os.path.join(BACKUP_ROOT, dir_name, rel_path(f))
    if os.path.exists(p1):
        return p1
    
    rel_out = os.path.relpath(f, OUT_DIR)
    if not rel_out.startswith('..'):
        p2 = os.path.join(BACKUP_ROOT, dir_name, rel_out)
        if os.path.exists(p2):
            return p2
    
    p3 = os.path.join(BACKUP_ROOT, dir_name, os.path.basename(f))
    return p3 if os.path.exists(p3) else None

def cmd_restore():
    dirs = find_backups()  # 已按时间倒序
    if not dirs:
        print('没有找到备份，无法还原。')
        return
    
    files = target_files()
    assets = os.path.join(OUT_DIR, 'renderer', 'assets')
    
    # 当前激活的 renderer 文件名集合(用于判定备份是否同 build)
    active = []
    try:
        active = os.listdir(assets)
    except:
        pass
    
    def same_build(dir_name: str) -> bool:
        ad = os.path.join(BACKUP_ROOT, dir_name, 'out', 'renderer', 'assets')
        try:
            names = os.listdir(ad)
            return any(a in names for a in active)
        except:
            return False
    
    restored = 0
    skipped = 0
    
    for f in files:
        is_chunk = os.path.dirname(f) == assets
        # 逐文件从"同 build 且英文原版"的备份中取副本:
        # 应用更新/稀疏备份/汉化中间态都会留下干扰项, 这里取简体字特征最少的那个
        best = None  # { src, zh }
        
        for dir_name in dirs:
            p = backup_copy_path(dir_name, f)
            if not p:
                continue
            if is_chunk and os.path.basename(p) != os.path.basename(f):
                continue  # 旧版 chunk 文件名不同
            if not is_chunk and not same_build(dir_name):
                continue  # 主进程/harness 需同 build 的备份目录
            
            with open(p, 'r', encoding='utf-8') as file:
                zh = zh_feature_count(file.read())
            
            if best is None or zh < best['zh']:
                best = {'src': p, 'zh': zh}
        
        if not best:
            print(f'  警告: 备份中没有可用于还原 {os.path.basename(f)} 的同版本文件，跳过')
            skipped += 1
            continue
        
        if best['zh'] > 100:
            print(f'  警告: {os.path.basename(f)} 的备份均为汉化后状态(特征字 {best["zh"]})，无法还原英文版，跳过')
            skipped += 1
            continue
        
        shutil.copy2(best['src'], f)
        restored += 1
    
    print(f'已还原 {restored} 个文件。' + (f'（跳过 {skipped} 个，详见上方警告）' if skipped else ''))

def cmd_status():
    print(f'应用目录: {APP_DIR}')
    backups = find_backups()
    if backups:
        print('备份: ' + '\n  '.join(os.path.join(BACKUP_ROOT, d) for d in backups))
    else:
        print('备份: 无')
    
    cn = is_chinese_app()
    print(f'汉化状态: {"已汉化" if cn else "未汉化（英文原版）"}')

def cmd_dry():
    report = apply_once(True)
    print(f"\n[试运行] 将替换 {report['total_replaced']} 处，涉及 {report['applied_terms']} 个词条。未写入任何文件。")

def main():
    if not init_globals():
        cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
        print('未找到 Command Code 安装目录。请通过以下任一方式指定:')
        print(f'  1. 命令行参数: python localize.py {cmd} "D:\\path\\to\\Command Code"')
        print('  2. 环境变量:   set CC_APP_DIR=D:\\path\\to\\Command Code')
        sys.exit(1)
    
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    
    if cmd == 'apply':
        cmd_apply()
    elif cmd == 'restore':
        cmd_restore()
    elif cmd == 'dry':
        cmd_dry()
    elif cmd == 'status':
        cmd_status()
    else:
        print('用法: python localize.py <apply|restore|status|dry> [安装目录]')

if __name__ == '__main__':
    main()

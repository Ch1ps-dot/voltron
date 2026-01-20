#!/bin/python3
import os
import argparse
from pathlib import Path

# 支持的代码文件类型及注释符号配置
# 格式: {文件后缀: (单行注释符列表, 多行注释开始符, 多行注释结束符)}
# 多行注释符为空表示不支持多行注释
COMMENT_CONFIG = {
    # 常见编程语言
    '.py': (['#'], '"""', '"""'),
    '.java': (['//'], '/*', '*/'),
    '.c': (['//'], '/*', '*/'),
    '.cpp': (['//'], '/*', '*/'),
    '.h': (['//'], '/*', '*/'),
    '.hpp': (['//'], '/*', '*/'),
    '.js': (['//'], '/*', '*/'),
    '.ts': (['//'], '/*', '*/'),
    '.html': (['<!--'], '<!--', '-->'),
    '.css': (['//'], '/*', '*/'),
    '.go': (['//'], '/*', '*/'),
    '.rb': (['#'], '=begin', '=end'),
    '.php': (['//', '#'], '/*', '*/'),
    '.swift': (['//'], '/*', '*/'),
    '.kt': (['//'], '/*', '*/'),
    '.scala': (['//'], '/*', '*/'),
    '.sh': (['#'], None, None),
    '.bash': (['#'], None, None),
    '.yml': (['#'], None, None),
    '.yaml': (['#'], None, None),
    '.json': ([], None, None),  # JSON无注释
    # '.xml': (['<!--'], '<!--', '-->'),
    '.md': ([], None, None)
}

# 默认排除的目录（常见的无关目录）
DEFAULT_EXCLUDE_DIRS = {
    '__pycache__', '.git', '.svn', '.hg', '.idea', 'node_modules',
    'venv', 'env', 'build', 'dist', 'target', 'out', '.vscode', '.logs', '.venv', 'test', 'equipment', 'tools'
}

# 默认排除的文件（临时/配置文件）
DEFAULT_EXCLUDE_FILES = {'.DS_Store', 'Thumbs.db'}


class CodeLineCounter:
    def __init__(self, root_dir, exclude_dirs=None, exclude_files=None, include_ext=None):
        """
        初始化代码行数统计器
        :param root_dir: 根目录
        :param exclude_dirs: 排除的目录集合
        :param exclude_files: 排除的文件集合
        :param include_ext: 只统计指定后缀的文件（None表示统计所有支持的类型）
        """
        self.root_dir = Path(root_dir).resolve()
        self.exclude_dirs = exclude_dirs or DEFAULT_EXCLUDE_DIRS
        self.exclude_files = exclude_files or DEFAULT_EXCLUDE_FILES
        self.include_ext = include_ext

        # 统计结果
        self.total_files = 0          # 总文件数
        self.total_lines = 0          # 总行数
        self.total_code_lines = 0     # 代码行数
        self.total_blank_lines = 0    # 空行数
        self.total_comment_lines = 0  # 注释行数

        # 按文件类型统计的明细
        self.type_stats = {}

    def is_excluded_dir(self, dir_path):
        """判断目录是否需要排除"""
        return any(excl in dir_path.parts for excl in self.exclude_dirs)

    def is_excluded_file(self, file_name):
        """判断文件是否需要排除"""
        return file_name in self.exclude_files

    def get_file_comment_config(self, ext):
        """获取文件类型对应的注释配置"""
        return COMMENT_CONFIG.get(ext, ([], None, None))

    def count_file_lines(self, file_path):
        """统计单个文件的行数"""
        ext = file_path.suffix.lower()
        single_line_comments, multi_start, multi_end = self.get_file_comment_config(ext)

        # 初始化文件级统计
        file_lines = 0
        file_code = 0
        file_blank = 0
        file_comment = 0
        in_multi_comment = False  # 是否在多行注释中

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    file_lines += 1
                    stripped_line = line.strip()

                    # 空行
                    if not stripped_line:
                        file_blank += 1
                        continue

                    # 处理多行注释
                    if multi_start and multi_end:
                        if in_multi_comment:
                            file_comment += 1
                            # 检查多行注释结束
                            if stripped_line.endswith(multi_end):
                                in_multi_comment = False
                            continue
                        # 检查多行注释开始
                        if stripped_line.startswith(multi_start):
                            file_comment += 1
                            # 多行注释未在本行结束
                            if not stripped_line.endswith(multi_end):
                                in_multi_comment = True
                            continue

                    # 处理单行注释
                    is_comment = False
                    for comment_char in single_line_comments:
                        if stripped_line.startswith(comment_char):
                            file_comment += 1
                            is_comment = True
                            break
                    if is_comment:
                        continue

                    # 代码行
                    file_code += 1

        except Exception as e:
            print(f"警告：读取文件 {file_path} 失败 - {e}")
            return

        # 更新总统计
        self.total_files += 1
        self.total_lines += file_lines
        self.total_code_lines += file_code
        self.total_blank_lines += file_blank
        self.total_comment_lines += file_comment

        # 更新按类型统计
        if ext not in self.type_stats:
            self.type_stats[ext] = {
                'files': 0, 'lines': 0, 'code': 0, 'blank': 0, 'comment': 0
            }
        self.type_stats[ext]['files'] += 1
        self.type_stats[ext]['lines'] += file_lines
        self.type_stats[ext]['code'] += file_code
        self.type_stats[ext]['blank'] += file_blank
        self.type_stats[ext]['comment'] += file_comment

        # 可选：打印单个文件统计（调试用）
        # print(f"{file_path}: 代码行={file_code}, 空行={file_blank}, 注释行={file_comment}")

    def run(self):
        """开始遍历并统计所有文件"""
        if not self.root_dir.exists():
            print(f"错误：目录 {self.root_dir} 不存在！")
            return

        # 遍历目录
        for file_path in self.root_dir.rglob('*'):
            # 跳过目录
            if file_path.is_dir():
                continue

            # 跳过排除的文件
            if self.is_excluded_file(file_path.name):
                continue

            # 跳过排除的目录下的文件
            if self.is_excluded_dir(file_path.parent):
                continue

            # 筛选指定后缀的文件
            ext = file_path.suffix.lower()
            if self.include_ext and ext not in self.include_ext:
                continue

            # 只统计支持注释配置的文件（避免统计二进制文件）
            if ext in COMMENT_CONFIG:
                self.count_file_lines(file_path)

        # 打印统计结果
        self.print_stats()

    def print_stats(self):
        """打印统计结果"""
        print("=" * 80)
        print(f"代码行数统计结果 (根目录: {self.root_dir})")
        print("=" * 80)
        print(f"总文件数: {self.total_files}")
        print(f"总行数: {self.total_lines}")
        print(f"代码行数: {self.total_code_lines} ({self.total_code_lines/self.total_lines*100:.1f}%)")
        print(f"空行数: {self.total_blank_lines} ({self.total_blank_lines/self.total_lines*100:.1f}%)")
        print(f"注释行数: {self.total_comment_lines} ({self.total_comment_lines/self.total_lines*100:.1f}%)")
        print("-" * 80)
        print("按文件类型统计明细：")
        print(f"{'类型':<10} {'文件数':<8} {'总行数':<10} {'代码行':<10} {'空行':<8} {'注释行':<10}")
        print("-" * 80)
        for ext, stats in sorted(self.type_stats.items(), key=lambda x: x[1]['lines'], reverse=True):
            ext_display = ext if ext else '其他'
            print(
                f"{ext_display:<10} {stats['files']:<8} {stats['lines']:<10} "
                f"{stats['code']:<10} {stats['blank']:<8} {stats['comment']:<10}"
            )
        print("=" * 80)


def main():
    # 命令行参数解析
    parser = argparse.ArgumentParser(description='统计项目代码行数工具')
    parser.add_argument('dir', nargs='?', default='.', help='要统计的目录（默认当前目录）')
    parser.add_argument(
        '--exclude-dirs', nargs='+', default=[],
        help='额外排除的目录（例如：--exclude-dirs test docs）'
    )
    parser.add_argument(
        '--exclude-files', nargs='+', default=[],
        help='额外排除的文件（例如：--exclude-files temp.txt debug.log）'
    )
    parser.add_argument(
        '--include-ext', nargs='+', default=None,
        help='只统计指定后缀的文件（例如：--include-ext .py .java）'
    )

    args = parser.parse_args()

    # 合并默认排除项和自定义排除项
    exclude_dirs = DEFAULT_EXCLUDE_DIRS.union(set(args.exclude_dirs))
    exclude_files = DEFAULT_EXCLUDE_FILES.union(set(args.exclude_files))

    # 初始化并运行统计器
    counter = CodeLineCounter(
        root_dir=args.dir,
        exclude_dirs=exclude_dirs,
        exclude_files=exclude_files,
        include_ext=args.include_ext
    )
    counter.run()


if __name__ == '__main__':
    main()
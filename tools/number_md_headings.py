#!/usr/bin/env python3
import re
import argparse
from pathlib import Path

def number_file(path: Path, inplace: bool=False, outpath: Path=None) -> Path:
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines()
    counters = [0]*6
    in_code = False
    out_lines = []

    for line in lines:
        # detect fenced code block start/end (```)
        if re.match(r'^\s*```', line):
            in_code = not in_code
            out_lines.append(line)
            continue

        if not in_code:
            m = re.match(r'^(\s{0,3})(#{1,6})\s*(.*)$', line)
            if m:
                lead, hashes, title = m.groups()
                level = len(hashes)
                counters[level-1] += 1
                # reset deeper levels
                for i in range(level, 6):
                    counters[i] = 0
                nums = [str(counters[i]) for i in range(level)]
                prefix = '.'.join(nums) + ' '
                out_lines.append(f"{lead}{prefix}{title}")
                continue

        out_lines.append(line)

    # preserve trailing newline if present
    trailing_nl = '\n' if text.endswith('\n') else ''
    out_text = '\n'.join(out_lines) + trailing_nl

    if inplace:
        path.write_text(out_text, encoding='utf-8')
        return path

    if outpath is None:
        stem = path.stem
        parent = path.parent
        outpath = parent / f"{stem}.numbered.md"

    outpath.write_text(out_text, encoding='utf-8')
    return outpath


def main():
    parser = argparse.ArgumentParser(description='Number Markdown headings (ATX style).')
    parser.add_argument('files', nargs='+', help='Markdown file(s) to process')
    parser.add_argument('-i', '--inplace', action='store_true', help='Replace original files')
    parser.add_argument('-o', '--output', help='Output path (for single input)')
    args = parser.parse_args()

    for idx, f in enumerate(args.files):
        p = Path(f)
        if not p.exists():
            print(f"Skipping missing file: {f}")
            continue
        outp = None
        if args.output:
            if len(args.files) > 1:
                print('Error: --output only allowed with single input')
                return
            outp = Path(args.output)
        result = number_file(p, inplace=args.inplace, outpath=outp)
        print(f"Wrote: {result}")


if __name__ == '__main__':
    main()

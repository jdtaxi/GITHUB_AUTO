import os
import sys

text = os.environ.get("INPUT_TEXT", "")
lines = text.splitlines()

print("=== Python 脚本开始 ===")
if not lines:
    print("未收到内容")
    sys.exit(0)

for i, line in enumerate(lines, 1):
    print(f"{i}: {line}")

print("=== Python 脚本结束 ===")

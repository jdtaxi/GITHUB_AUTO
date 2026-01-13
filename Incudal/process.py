import os

text = os.environ.get("INPUT_TEXT", "")
lines = text.splitlines()

result = []
for i, line in enumerate(lines, 1):
    result.append(f"{i}: {line}")

# 你真正要回传的内容
message = "\n".join(result)

# 写入文件（Actions 用来读取）
with open("result.txt", "w", encoding="utf-8") as f:
    f.write(message)

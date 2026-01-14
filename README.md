GH_2FA_SECRET
-二次验证码
GH_PASSWORD
-账户密码
GH_USERNAME
-账户名
PROXY
-代理
REPO_TOKEN
-具有repo权限的token
TG_BOT_TOKEN

TG_CHAT_ID

# 假设从 GitHub 下载了加密文件
with open("config.enc", "r", encoding="utf-8") as f:
    encrypted_content = f.read()

password = "MY_SUPER_SECRET_KEY"

try:
    data = decrypt_json(encrypted_content, password)
    print("✅ 解密成功:", data)
except ValueError as e:
    print("❌ 解密失败:", e)

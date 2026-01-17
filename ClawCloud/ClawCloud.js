/**
 * ClawCloud 登录保活脚本 (GitHub Actions 适配版)
 * 保持原变量 CONFIG 与逻辑不变
 */

const axios = require('axios');
const puppeteer = require("puppeteer"); // GitHub 环境使用标准 puppeteer

// ==================== 配置 (变量保持不变) ====================
const CONFIG = {
    CLAW_CLOUD_URL: process.env.CLAW_CLOUD_URL || "https://ap-southeast-1.run.claw.cloud",
    GH_USERNAME: process.env.GH_USERNAME || "jdtaxi",
    GH_PASSWORD: process.env.GH_PASSWORD || "you60600276",
    TG_BOT_TOKEN: process.env.TG_BOT_TOKEN || "8525533877:AAGJDqO5TmqtJatwW-tZoDcc8LPtLVVcD8Y",
    TG_CHAT_ID: process.env.TG_CHAT_ID || 1966630851,
    TWO_FACTOR_WAIT: 120 
};

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// ==================== Telegram 交互 (逻辑保持不变) ====================
async function get2FACode(token, chatId, timeoutSec) {
    console.log(`🔹 正在等待 TG 验证码 (/code xxxxxx)...`);
    let offset = 0;
    const deadline = Date.now() + timeoutSec * 1000;
    while (Date.now() < deadline) {
        try {
            const res = await axios.get(`https://api.telegram.org/bot${token}/getUpdates`, { 
                params: { timeout: 10, offset },
                timeout: 15000 
            });
            if (res.data.ok && res.data.result.length > 0) {
                for (const upd of res.data.result) {
                    offset = upd.update_id + 1;
                    const text = upd.message?.text || "";
                    if (String(upd.message?.chat?.id) === String(chatId) && text.startsWith('/code')) {
                        console.log("🔹 收到验证码: ", text.replace('/code', '').trim());
                        return text.replace('/code', '').trim();
                    }
                }
            }
        } catch (e) {}
        await sleep(4000);
    }
    return null;
}

// ==================== 核心逻辑 ====================
async function run() {
    console.log(`🚀 任务启动: ${new Date().toLocaleString()}`);
    
    // GitHub Actions 适配：使用标准的 Puppeteer 启动参数
    const browser = await puppeteer.launch({
        headless: "new",
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    const page = await browser.newPage();

    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    await page.setViewport({ width: 1280, height: 800 });
    page.setDefaultTimeout(60000); // 增加到 60s 以适配 GitHub 网络

    try {
        // 1. 进入登录页
        console.log("🔹 步骤 1: 访问 ClawCloud...");
        await page.goto(`${CONFIG.CLAW_CLOUD_URL}/signin`, { waitUntil: 'networkidle2' });

        // 2. 等待并点击 GitHub 按钮
        console.log("🔹 步骤 2: 等待 GitHub 登录按钮渲染...");
        await page.waitForFunction(() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            return buttons.some(btn => btn.innerText.includes('GitHub'));
        }, { timeout: 20000 });

        const clicked = await page.evaluate(() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const githubBtn = buttons.find(btn => btn.innerText.includes('GitHub'));
            if (githubBtn) {
                githubBtn.click();
                return true;
            }
            return false;
        });

        if (!clicked) throw new Error("无法点击 GitHub 按钮");
        console.log("✅ 已点击 GitHub 按钮");

        // 3. GitHub 登录表单处理
        console.log("🔹 步骤 3: 等待 GitHub 登录页面跳转...");
        await page.waitForNavigation({ waitUntil: 'networkidle2' });

        if (page.url().includes('github.com/login')) {
            console.log("🔹 步骤 4: 输入 GitHub 账号密码...");
            await page.waitForSelector('#login_field', { visible: true });
            await page.type('#login_field', CONFIG.GH_USERNAME, { delay: 50 });
            await page.type('#password', CONFIG.GH_PASSWORD, { delay: 50 });
            await Promise.all([
                page.click('input[type="submit"]'),
                page.waitForNavigation({ waitUntil: 'networkidle2' })
            ]);
        }

        // 4. 处理 2FA
        if (page.url().includes('two-factor')) {
            console.log("⚠️ 步骤 5: 检测到 2FA 验证码需求");
            if (CONFIG.TG_BOT_TOKEN) {
                await axios.post(`https://api.telegram.org/bot${CONFIG.TG_BOT_TOKEN}/sendMessage`, {
                    chat_id: CONFIG.TG_CHAT_ID,
                    text: "🔐 <b>ClawCloud 2FA 验证</b>\n请发送：<code>/code 123456</code>",
                    parse_mode: "HTML"
                }).catch(() => {});
            }

            const code = await get2FACode(CONFIG.TG_BOT_TOKEN, CONFIG.TG_CHAT_ID, CONFIG.TWO_FACTOR_WAIT);
            if (!code) throw new Error("2FA 验证码获取超时");

            await page.type('#otp, input[name="app_otp"]', code, { delay: 50 });
            await page.keyboard.press('Enter');
            await page.waitForNavigation({ waitUntil: 'networkidle2' });
        }

        // 5. 检查 OAuth 授权
        if (page.url().includes('oauth/authorize')) {
            console.log("🔹 步骤 6: 检查 OAuth 授权确认...");
            try {
                await page.waitForSelector('button#js-oauth-authorize-btn', { timeout: 5000 });
                await page.click('button#js-oauth-authorize-btn');
                await page.waitForNavigation({ waitUntil: 'networkidle2' });
            } catch (e) {
                console.log("ℹ️ 无需手动授权，已自动跳转");
            }
        }

        // 6. 验证最终状态
        console.log("🔹 步骤 7: 确认 Dashboard 状态...");
        await page.goto(`${CONFIG.CLAW_CLOUD_URL}/dashboard`, { waitUntil: 'networkidle2' });
        
        if (page.url().includes('dashboard') || page.url().includes('apps')) {
            console.log("✅ ClawCloud 登录保活成功！");
            if (CONFIG.TG_BOT_TOKEN) {
                await axios.post(`https://api.telegram.org/bot${CONFIG.TG_BOT_TOKEN}/sendMessage`, {
                    chat_id: CONFIG.TG_CHAT_ID,
                    text: "✅ <b>ClawCloud 登录保活成功</b>",
                    parse_mode: "HTML"
                }).catch(() => {});
            }
        } else {
            throw new Error(`最终页面 URL 异常: ${page.url()}`);
        }

    } catch (e) {
        console.error(`❌ 任务失败: ${e.message}`);
        if (CONFIG.TG_BOT_TOKEN) {
            await axios.post(`https://api.telegram.org/bot${CONFIG.TG_BOT_TOKEN}/sendMessage`, {
                chat_id: CONFIG.TG_CHAT_ID,
                text: `❌ <b>ClawCloud 任务异常</b>\n原因: ${e.message}`
            }).catch(() => {});
        }
    } finally {
        await browser.close();
        console.log("🏁 任务结束");
    }
}

run();

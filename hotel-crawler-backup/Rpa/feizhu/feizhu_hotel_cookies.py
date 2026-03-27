# -*- coding: utf-8 -*-
"""
飞猪酒店 Cookies 管理工具
用于手动登录并保存Cookies，或测试已保存的Cookies是否有效
"""

import pickle
import os
import yaml
import time
import logging
from playwright.sync_api import sync_playwright

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.yaml")
COOKIES_FILE = os.path.join(SCRIPT_DIR, "feizhu_hotel_cookies.pkl")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config():
    """加载配置文件"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logger.error(f"❌ 配置文件加载失败: {e}")
        logger.error(f"   请确保 {CONFIG_FILE} 文件存在且格式正确")
        return None


def setup_browser(headless=False, use_persistent=True, config=None):
    """
    启动浏览器
    
    参数:
        headless: 是否无头模式
        use_persistent: 是否使用持久化上下文（非无痕模式）
        config: 配置字典（可选）
    """
    playwright = sync_playwright().start()
    
    # 从配置中读取浏览器设置
    browser_config = config.get('browser', {}) if config else {}
    use_local_chrome = browser_config.get('use_local_chrome', False)
    chrome_executable = browser_config.get('chrome_executable', '')
    user_data_dir_config = browser_config.get('user_data_dir', '')
    profile_directory = browser_config.get('profile_directory', 'Default')
    
    # 用户数据目录（用于持久化上下文）
    # 优先使用本地 Chrome 的用户数据目录，这样更不容易被检测
    if use_local_chrome and user_data_dir_config:
        # 使用本地用户数据目录（推荐：使用真实浏览器的用户数据）
        user_data_dir = user_data_dir_config
        logger.info(f"使用本地用户数据目录: {user_data_dir}")
        logger.info("   提示：使用本地Chrome用户数据可以降低被检测概率")
    else:
        # 使用项目目录下的用户数据目录
        user_data_dir = os.path.join(SCRIPT_DIR, "browser_data")
        logger.warning("⚠️  建议在 config.yaml 中配置 use_local_chrome 和 user_data_dir")
        logger.warning("   使用本地Chrome用户数据可以降低被检测为自动化工具的概率")
    
    if use_persistent:
        # 使用持久化上下文（非无痕模式，会保存登录态、历史记录等）
        # 注意：launch_persistent_context 不支持 executable_path，只能使用 Playwright 自带的 Chromium
        # 但可以使用本地用户数据目录，这样就能访问已有的登录态
        launch_options = {
            'user_data_dir': user_data_dir,
            'headless': headless,
            'slow_mo': 500,
            'viewport': {'width': 1920, 'height': 1080},
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
            ],
        }
        
        # launch_persistent_context 不支持 executable_path，只能使用 Playwright Chromium
        # 但通过使用本地用户数据目录，可以访问已有的登录态和设置
        logger.info("使用 Playwright Chromium + 本地用户数据目录")
        
        context = playwright.chromium.launch_persistent_context(**launch_options)
        browser = None  # 持久化上下文不需要单独的browser对象
        page = context.new_page()
        
        # 添加反检测脚本
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 覆盖 plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // 覆盖 languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
            
            // 覆盖 permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)
        
        return playwright, browser, context, page
    else:
        # 使用临时上下文（无痕模式）
        launch_options = {
            'headless': headless,
            'slow_mo': 500
        }
        
        # 临时上下文可以使用 executable_path
        if use_local_chrome and chrome_executable and os.path.exists(chrome_executable):
            launch_options['executable_path'] = chrome_executable
            logger.info(f"使用本地Chromium: {chrome_executable}")
        elif use_local_chrome:
            try:
                launch_options['channel'] = 'chrome'
                logger.info("使用系统Chrome（通过channel）")
            except:
                logger.warning("未找到系统Chrome，使用Playwright Chromium")
        
        browser = playwright.chromium.launch(**launch_options)
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
        )
        
        page = context.new_page()
        
        # 添加反检测脚本
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 覆盖 plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // 覆盖 languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
            
            // 覆盖 permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)
        
        return playwright, browser, context, page


def save_cookies(context):
    """保存cookies到文件"""
    try:
        cookies = context.cookies()
        with open(COOKIES_FILE, 'wb') as f:
            pickle.dump(cookies, f)
        logger.info(f"✓ Cookies已保存到 {COOKIES_FILE}")
        logger.info(f"  共 {len(cookies)} 个cookie")
        return True
    except Exception as e:
        logger.error(f"❌ 保存Cookies失败: {e}")
        return False


def load_cookies(context, url):
    """从文件加载cookies"""
    if not os.path.exists(COOKIES_FILE):
        return False
    
    try:
        with open(COOKIES_FILE, 'rb') as f:
            cookies = pickle.load(f)
        
        # Playwright 加载cookies需要先访问对应域名
        # 从URL中提取域名和协议
        from urllib.parse import urlparse
        parsed = urlparse(url)
        
        # 确保URL格式正确
        if not parsed.scheme:
            # 如果没有协议，添加https
            url = 'https://' + url
            parsed = urlparse(url)
        
        scheme = parsed.scheme or 'https'
        domain = parsed.netloc or parsed.hostname
        
        if not domain:
            logger.warning("⚠️ 无法从URL中提取域名")
            return False
        
        # 构建基础URL（协议+域名）
        base_url = f"{scheme}://{domain}"
        
        # 先访问域名（加载cookies需要先访问对应域名）
        try:
            page = context.new_page()
            page.goto(base_url, timeout=30000)
            time.sleep(1)
            page.close()
        except Exception as e:
            logger.warning(f"⚠️ 访问域名失败，尝试直接加载cookies: {e}")
            # 即使访问失败，也尝试加载cookies
        
        # 加载cookies
        context.add_cookies(cookies)
        logger.info(f"✓ 已加载 {len(cookies)} 个cookie")
        return True
    except Exception as e:
        logger.warning(f"⚠️ 加载Cookies失败: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False


def login_and_save():
    """登录并保存cookies（交互式）"""
    print("=" * 60)
    print("  飞猪酒店登录工具（保存Cookies）")
    print("=" * 60)
    
    # 加载配置
    config = load_config()
    if not config:
        # 如果没有配置文件，使用默认URL
        default_url = "https://hotel.fliggy.com/ebooking/login.htm#/?redirectURL=https%3A%2F%2Fhotel.fliggy.com%2Febooking%2FhotelBaseInfoUv.htm"
        logger.info(f"使用默认登录URL: {default_url}")
        config = {
            'login': {
                'url': default_url
            },
            'browser': {
                'use_persistent': True
            }
        }
    
    login_config = config.get('login', {})
    url = login_config.get('url', 'https://hotel.fliggy.com/ebooking/login.htm#/?redirectURL=https%3A%2F%2Fhotel.fliggy.com%2Febooking%2FhotelBaseInfoUv.htm')
    
    if not url:
        logger.error("❌ 配置文件中未设置登录URL")
        logger.error("   请在 config.yaml 中设置 login.url")
        return
    
    # 加载浏览器配置
    browser_config = config.get('browser', {}) if config else {}
    
    playwright, browser, context, page = setup_browser(
        headless=False,
        use_persistent=browser_config.get('use_persistent', True),
        config=config
    )
    
    try:
        # 先尝试加载已有的cookies
        if os.path.exists(COOKIES_FILE):
            print("\n发现已保存的Cookies，正在加载...")
            load_cookies(context, url)
        
        print(f"\n正在打开登录页面: {url}")
        # 先访问首页，让浏览器看起来更自然
        try:
            base_url = "https://hotel.fliggy.com"
            page.goto(base_url, wait_until='domcontentloaded', timeout=30000)
            time.sleep(2)
        except:
            pass
        
        # 再访问登录页面
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
        time.sleep(5)  # 增加等待时间，让页面完全加载
        
        # 检查是否有验证失败的错误提示
        try:
            error_elements = page.locator('text=/验证失败|点击框体重试|error:/i')
            if error_elements.count() > 0:
                print("\n⚠️  检测到验证失败提示")
                print("   可能遇到了验证码或风控验证")
                print("   请在浏览器中手动处理验证（如点击验证框、完成滑块验证等）")
                print("   处理完成后，页面会自动刷新或跳转")
                input("\n处理完验证后，按回车继续...")
                time.sleep(2)
                # 刷新页面
                page.reload(wait_until='networkidle', timeout=60000)
                time.sleep(3)
        except:
            pass
        
        # 检查是否需要登录
        current_url = page.url
        page_text = page.locator('body').text_content() or ''
        
        # 检查URL是否包含登录相关路径
        needs_login = '/login' in current_url.lower() or 'login' in current_url.lower()
        
        # 检查页面文本中是否有登录相关文字
        if not needs_login:
            needs_login = '登录' in page_text or 'login' in page_text.lower() or '请登录' in page_text
        
        # 检查是否已登录（飞猪酒店后台通常会有特定的元素）
        is_logged_in = False
        try:
            # 检查是否有用户信息或退出按钮
            user_elements = page.locator('text=/用户|退出|我的|账户/i').first
            if user_elements.count() > 0:
                is_logged_in = True
        except:
            pass
        
        if needs_login and not is_logged_in:
            print("\n⚠️  检测到未登录状态")
            print("   请在浏览器中完成登录操作")
            print("   如果遇到验证码或滑块验证，请手动完成")
        else:
            print("\n✓ 检测到可能已登录状态")
            print("   如果实际未登录，请在浏览器中完成登录")
        
        print("\n操作说明：")
        print("  - 如果未登录，请在浏览器中完成登录（可能需要扫码或输入账号密码）")
        print("  - 如果遇到验证码、滑块验证等，请手动完成验证")
        print("  - 如果出现'验证失败'提示，请点击验证框重试")
        print("  - 登录成功后，页面会跳转到酒店后台首页")
        print("  - 确认已登录后，按回车保存Cookies")
        print("\n💡 提示：如果频繁遇到验证失败，建议在 config.yaml 中配置 use_local_chrome: true")
        print("   并使用真实Chrome浏览器的用户数据目录")
        input("\n确认已登录后，按回车保存Cookies >>> ")
        
        # 再次检查登录状态
        current_url = page.url
        page_text = page.locator('body').text_content() or ''
        
        # 再次检查是否有验证失败提示
        try:
            error_elements = page.locator('text=/验证失败|点击框体重试|error:/i')
            if error_elements.count() > 0:
                print("\n⚠️  警告：检测到验证失败提示")
                print("   当前可能仍在验证页面")
                print("   请确认是否已完成验证和登录")
                confirm = input("   是否继续保存Cookies？(y/n): ")
                if confirm.lower() != 'y':
                    print("已取消保存")
                    return
        except:
            pass
        
        # 检查是否还在登录页
        if '/login' in current_url.lower() and 'hotelBaseInfoUv' not in current_url:
            print("\n⚠️  警告：当前仍在登录页面")
            print("   请确认是否已完成登录")
            confirm = input("   是否继续保存Cookies？(y/n): ")
            if confirm.lower() != 'y':
                print("已取消保存")
                return
        
        # 保存cookies
        if save_cookies(context):
            print("\n✅ Cookies已保存！")
            print(f"   文件位置: {COOKIES_FILE}")
            print("   下次运行RPA脚本时会自动使用这些Cookies")
        else:
            print("\n❌ Cookies保存失败")
        
        input("\n按回车关闭浏览器...")
        
    except Exception as e:
        logger.error(f"❌ 操作失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        if browser:
            browser.close()
        else:
            # 持久化上下文需要关闭context
            context.close()
        playwright.stop()


def test_cookies():
    """测试保存的cookies是否有效"""
    print("=" * 60)
    print("  测试保存的Cookies")
    print("=" * 60)
    
    if not os.path.exists(COOKIES_FILE):
        print("\n❌ 未找到cookies文件")
        print(f"   文件位置: {COOKIES_FILE}")
        print("   请先运行登录工具: python feizhu_hotel_cookies.py")
        return
    
    # 加载配置
    config = load_config()
    if not config:
        default_url = "https://hotel.fliggy.com/ebooking/login.htm#/?redirectURL=https%3A%2F%2Fhotel.fliggy.com%2Febooking%2FhotelBaseInfoUv.htm"
        config = {
            'login': {
                'url': default_url
            },
            'browser': {
                'use_persistent': True
            }
        }
    
    login_config = config.get('login', {})
    url = login_config.get('url', 'https://hotel.fliggy.com/ebooking/login.htm')
    
    if not url:
        logger.error("❌ 配置文件中未设置登录URL")
        return
    
    # 加载浏览器配置
    browser_config = config.get('browser', {}) if config else {}
    
    playwright, browser, context, page = setup_browser(
        headless=False,
        use_persistent=browser_config.get('use_persistent', True),
        config=config
    )
    
    try:
        print("\n正在加载cookies...")
        if not load_cookies(context, url):
            print("❌ Cookies加载失败")
            return
        
        # 访问登录后的页面（如dashboard、首页等）
        from urllib.parse import urlparse
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # 尝试访问酒店后台首页
        test_url = "https://hotel.fliggy.com/ebooking/hotelBaseInfoUv.htm"
        
        print(f"正在访问测试页面: {test_url}")
        page.goto(test_url, wait_until='networkidle', timeout=60000)
        time.sleep(3)
        
        current_url = page.url
        page_text = page.locator('body').text_content() or ''
        
        # 检查是否被重定向到登录页
        if '/login' in current_url.lower() and 'hotelBaseInfoUv' not in current_url:
            print("\n❌ Cookies已失效")
            print("   检测到被重定向到登录页面")
            print("   请重新运行登录工具: python feizhu_hotel_cookies.py")
        elif '登录' in page_text or 'login' in page_text.lower() or '请登录' in page_text:
            print("\n⚠️  Cookies可能已失效")
            print("   页面中检测到登录相关文字")
            print("   请检查浏览器中的实际状态")
        else:
            print("\n✅ Cookies有效！登录成功")
            print("   当前页面: " + current_url[:80])
        
        input("\n按回车关闭浏览器...")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        if browser:
            browser.close()
        else:
            # 持久化上下文需要关闭context
            context.close()
        playwright.stop()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_cookies()
    else:
        login_and_save()

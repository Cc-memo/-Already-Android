"""
登录认证核心模块 - 可复用
"""
from typing import Optional, Dict, Any
from selenium.webdriver.common.by import By
import time

from crawler.utils.logger import logger
from crawler.core.browser import BrowserManager


class AuthManager:
    """登录认证管理器 - 可复用"""
    
    def __init__(self, browser: BrowserManager):
        """
        初始化认证管理器
        
        Args:
            browser: 浏览器管理器实例
        """
        self.browser = browser
    
    def login(self, platform: str, username: str, password: str, 
              login_config: Dict[str, Any]) -> bool:
        """
        通用登录方法
        
        Args:
            platform: 平台名称
            username: 用户名
            password: 密码
            login_config: 登录配置，包含：
                - login_url: 登录页面URL
                - username_selector: 用户名输入框选择器
                - password_selector: 密码输入框选择器
                - submit_selector: 提交按钮选择器
                - success_selector: 登录成功后的标识元素选择器（可选）
                - captcha_selector: 验证码输入框选择器（可选）
                - need_switch_to_frame: 是否需要切换iframe（可选）
                - frame_selector: iframe选择器（可选）
        
        Returns:
            是否登录成功
        """
        try:
            logger.info(f"{platform} 开始登录流程")
            
            # 打开登录页面
            if not self.browser.get(login_config['login_url']):
                return False
            
            time.sleep(2)  # 等待页面加载
            
            # 切换iframe（如果需要）
            if login_config.get('need_switch_to_frame'):
                frame_selector = login_config.get('frame_selector', 'iframe')
                iframe = self.browser.find_element(frame_selector)
                if iframe:
                    self.browser.driver.switch_to.frame(iframe)
                    logger.info("已切换到登录iframe")
            
            # 输入用户名
            if not self.browser.input_text(
                login_config['username_selector'],
                username,
                by=By.CSS_SELECTOR
            ):
                logger.error(f"{platform} 输入用户名失败")
                return False
            
            time.sleep(0.5)
            
            # 输入密码
            if not self.browser.input_text(
                login_config['password_selector'],
                password,
                by=By.CSS_SELECTOR
            ):
                logger.error(f"{platform} 输入密码失败")
                return False
            
            time.sleep(0.5)
            
            # 处理验证码（如果需要）
            if login_config.get('captcha_selector'):
                logger.warning(f"{platform} 需要输入验证码，请手动处理")
                # 等待用户手动输入验证码
                time.sleep(10)
            
            # 点击登录按钮
            if not self.browser.click(login_config['submit_selector']):
                logger.error(f"{platform} 点击登录按钮失败")
                return False
            
            time.sleep(3)  # 等待登录完成
            
            # 切换回主frame（如果之前切换了）
            if login_config.get('need_switch_to_frame'):
                self.browser.driver.switch_to.default_content()
            
            # 验证登录是否成功
            if login_config.get('success_selector'):
                if self.browser.wait_for_element(login_config['success_selector'], timeout=10):
                    logger.info(f"{platform} 登录成功")
                    return True
                else:
                    logger.error(f"{platform} 登录失败：未找到成功标识元素")
                    return False
            else:
                # 如果没有成功标识，检查URL变化
                current_url = self.browser.get_current_url()
                if 'login' not in current_url.lower():
                    logger.info(f"{platform} 登录成功（通过URL判断）")
                    return True
                else:
                    logger.warning(f"{platform} 登录状态不确定")
                    return True  # 假设成功，实际使用时需要根据具体情况调整
            
        except Exception as e:
            logger.error(f"{platform} 登录过程出错: {e}")
            return False
    
    def is_logged_in(self, check_selector: str) -> bool:
        """
        检查是否已登录
        
        Args:
            check_selector: 检查登录状态的元素选择器
        
        Returns:
            是否已登录
        """
        element = self.browser.find_element(check_selector)
        return element is not None
    
    def logout(self, logout_selector: Optional[str] = None):
        """
        退出登录
        
        Args:
            logout_selector: 退出登录按钮选择器（可选）
        """
        if logout_selector:
            self.browser.click(logout_selector)
            logger.info("已退出登录")
        else:
            # 清除cookies
            self.browser.driver.delete_all_cookies()
            logger.info("已清除登录状态")


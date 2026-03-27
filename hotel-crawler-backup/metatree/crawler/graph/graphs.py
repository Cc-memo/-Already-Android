"""
LangGraph流程图定义
"""
from typing import Literal
from langgraph.graph import StateGraph, END
from .state import CrawlState
from .agents import (
    URLFetcherAgent,
    LoginAgent,
    LocatorAgent,
    SearchAgent,
    ExtractorAgent,
    ValidatorAgent,
    ErrorHandlerAgent
)
from crawler.core.browser import BrowserManager
from crawler.config.settings import CRAWLER_CONFIG
from loguru import logger


def should_login(state: CrawlState) -> Literal["login", "locate_elements"]:
    """判断是否需要登录"""
    if state.login_credentials and state.login_credentials.get('username'):
        return "login"
    return "locate_elements"


def should_retry(state: CrawlState) -> Literal["retry", "fail"]:
    """判断是否重试"""
    if state.error_count < state.max_retries:
        return "retry"
    return "fail"


def create_base_graph(platform: str, browser: BrowserManager = None) -> StateGraph:
    """创建基础流程图"""
    
    # 创建角色实例
    url_fetcher = URLFetcherAgent(browser)
    login_agent = LoginAgent(browser)
    locator = LocatorAgent(browser)
    search = SearchAgent(browser)
    extractor = ExtractorAgent(browser)
    validator = ValidatorAgent(browser)
    error_handler = ErrorHandlerAgent(browser)
    
    # 创建状态图
    workflow = StateGraph(CrawlState)
    
    # 添加节点
    workflow.add_node("fetch_urls", url_fetcher.execute)
    workflow.add_node("login", login_agent.execute)
    workflow.add_node("locate_elements", locator.execute)
    workflow.add_node("search_hotel", search.execute)
    workflow.add_node("extract_data", extractor.execute)
    workflow.add_node("validate_content", validator.execute)
    workflow.add_node("handle_error", error_handler.execute)
    
    # 设置入口
    workflow.set_entry_point("fetch_urls")
    
    # 添加边
    workflow.add_conditional_edges(
        "fetch_urls",
        should_login,
        {
            "login": "login",
            "locate_elements": "locate_elements"
        }
    )
    
    workflow.add_edge("login", "locate_elements")
    workflow.add_edge("locate_elements", "search_hotel")
    workflow.add_edge("search_hotel", "extract_data")
    workflow.add_edge("extract_data", "validate_content")
    workflow.add_edge("validate_content", END)
    
    # 错误处理边
    workflow.add_conditional_edges(
        "handle_error",
        should_retry,
        {
            "retry": "fetch_urls",  # 重试从开始
            "fail": END
        }
    )
    
    return workflow


def create_meituan_graph(browser: BrowserManager = None) -> StateGraph:
    """创建美团平台流程图"""
    graph = create_base_graph("meituan", browser)
    graph = graph.compile()
    return graph


def create_ctrip_graph(browser: BrowserManager = None) -> StateGraph:
    """创建携程平台流程图"""
    graph = create_base_graph("ctrip", browser)
    graph = graph.compile()
    return graph


def create_fliggy_graph(browser: BrowserManager = None) -> StateGraph:
    """创建飞猪平台流程图"""
    graph = create_base_graph("fliggy", browser)
    graph = graph.compile()
    return graph


def create_gaode_graph(browser: BrowserManager = None) -> StateGraph:
    """创建高德平台流程图"""
    graph = create_base_graph("gaode", browser)
    graph = graph.compile()
    return graph


def get_graph_for_platform(platform: str, browser: BrowserManager = None) -> StateGraph:
    """根据平台获取对应的流程图"""
    graph_creators = {
        'meituan': create_meituan_graph,
        'ctrip': create_ctrip_graph,
        'fliggy': create_fliggy_graph,
        'gaode': create_gaode_graph,
    }
    
    creator = graph_creators.get(platform)
    if not creator:
        raise ValueError(f"不支持的平台: {platform}")
    
    return creator(browser)


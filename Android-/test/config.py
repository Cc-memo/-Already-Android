# -*- coding: utf-8 -*-
"""手机端调度配置：Web Admin 地址、轮询间隔"""
import os

# Web Admin 根地址（领任务 / 上报用）
BASE_URL = os.environ.get("APP_SCHEDULER_BASE_URL", os.environ.get("LOCAL_TASKS_BASE_URL", "http://localhost:5000"))

# 轮询间隔（秒）
POLL_INTERVAL = int(os.environ.get("APP_SCHEDULER_POLL_INTERVAL", "30"))

# 项目根目录（test 的上一级，即 Android-）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

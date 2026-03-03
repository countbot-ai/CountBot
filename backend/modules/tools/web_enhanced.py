"""Enhanced Web Tools - 增强的网页工具
整合 scrapling-fetch-mcp 的所有功能，支持反爬虫和 JavaScript 渲染
"""

import json
import os
from contextlib import redirect_stdout
from functools import reduce
from re import compile as re_compile
from re import error as re_error
from re import search as re_search
from typing import Any, Optional
from urllib.parse import quote, unquote, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from markdownify import ATX, MarkdownConverter, chomp

from backend.modules.tools.base import Tool

# ================================================
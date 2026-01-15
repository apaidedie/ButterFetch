# /// script
# dependencies = ["ttkbootstrap", "requests", "beautifulsoup4", "Pillow", "urllib3"]
# ///
"""
ButterFetch - 黄油搜索工具
支持 DLsite / FANZA / VNDB 三平台并行搜索
"""

import sys
import os
import io
import re
import gc
import json
import random
import threading
import webbrowser
import ctypes
import logging
import atexit
from abc import ABC, abstractmethod
from urllib.parse import quote
from typing import List, Dict, Optional, Tuple, Any, Set, Callable
from functools import wraps
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from tkinter import messagebox, filedialog

import requests
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw
from bs4 import BeautifulSoup
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter


# ============================================================================
# 工具函数
# ============================================================================

def resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def setup_logger() -> logging.Logger:
    """配置日志系统"""
    _logger = logging.getLogger("ButterFetch")
    _logger.setLevel(logging.INFO)
    
    if _logger.handlers:
        return _logger
    
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'，
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    try:
        file_handler = logging.FileHandler(
            resource_path("butterfetch.log"),
            encoding='utf-8',
            mode='a'
        )
        file_handler.setFormatter(formatter)
        _logger.addHandler(file_handler)
    except Exception:
        pass
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    _logger.addHandler(console_handler)
    
    return _logger


logger = setup_logger()


def set_app_user_model_id() -> None:
    """设置 Windows 任务栏应用 ID"""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            'personal.butterfetch.moe.v2.0'
        )
    except Exception:
        pass


def set_dpi_awareness() -> None:
    """设置 DPI 感知"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


set_app_user_model_id()
set_dpi_awareness()


# ============================================================================
# 枚举与常量
# ============================================================================

class SearchSource(Enum):
    """搜索来源枚举"""
    DLSITE = "DLsite"
    FANZA = "FANZA"
    VNDB = "VNDB"


class SearchState(Enum):
    """搜索状态"""
    IDLE = "idle"
    SEARCHING = "searching"
    SUCCESS = "success"
    ERROR = "error"
    NO_RESULT = "no_result"


class UIText:
    """UI 文本常量"""
    LOADING = "🔄 加载中..."
    SEARCHING = "🔍 并行搜索中..."
    SEARCHING_CAT = "🐱 正在全力寻找喵..."
    NO_RESULT = "无结果"
    NOT_FOUND = "😿 呜呜...什么都没找到..."
    IMAGE_FAILED = "[😭 图片跑丢了]"
    READY = "✨ Ready..."
    WAITING = "等待搜索..."
    TITLE_COPIED = "标题已复制!"
    LOG_VIEW = "📜 日志"
    LOG_BACK = "🔙 返回"
    LOG_EMPTY = "📭 暂无日志记录喵~"


class Colors:
    """颜色常量"""
    SAKURA = "#FF9CAE"
    SKY = "#A0D8EF"
    GRAPE = "#9b59b6"
    TEXT = "#555555"
    CLEAR_NORMAL = "#FFBCBC"
    CLEAR_HOVER = "#FF6B8B"
    LIGHT_BG = "white"
    DARK_BG = "#303030"


class Timeouts:
    """超时配置"""
    REQUEST = 8
    IMAGE = 10
    DEBOUNCE_MS = 300
    TOAST_DURATION_MS = 1200
    LOG_REFRESH_MS = 2000


class Limits:
    """数量限制配置"""
    MAX_RESULTS = 5
    MAX_WORKERS = 4
    RETRY_TIMES = 3
    RETRY_BACKOFF = 0.5
    POOL_CONNECTIONS = 5
    POOL_MAXSIZE = 10
    IMAGE_CACHE_SIZE = 20
    MEMORY_THRESHOLD_MB = 200
    SEARCH_CACHE_SIZE = 10


class UISize:
    """UI 尺寸配置"""
    IMG_HEIGHT = 420
    CORNER_RADIUS = 25


class APIEndpoints:
    """API 端点配置"""
    VNDB_API = "https://api.vndb.org/kana/vn"
    DLSITE_BASE = "https://www.dlsite.com"
    DLSITE_MODES = ("maniax", "pro")
    FANZA_SEARCH = "https://www.dmm.co.jp/search/=/searchstr={}/floor=digital/group=adult/"
    FANZA_DETAIL = "https://dlsoft.dmm.co.jp/detail/{}/"
    
    @classmethod
    def dlsite_search(cls, mode: str, keyword: str) -> str:
        return f"{cls.DLSITE_BASE}/{mode}/fsr/=/keyword/{quote(keyword)}/order/trend"
    
    @classmethod
    def dlsite_product(cls, mode: str, gid: str) -> str:
        return f"{cls.DLSITE_BASE}/{mode}/work/=/product_id/{gid}.html"
    
    @classmethod
    def fanza_search(cls, keyword: str) -> str:
        return cls.FANZA_SEARCH.format(quote(keyword, encoding='utf-8'))
    
    @classmethod
    def fanza_detail(cls, gid: str) -> str:
        return cls.FANZA_DETAIL.format(gid)


class Cookies:
    """请求 Cookies 配置"""
    DLSITE = {"adult_checked": "1", "locale": "ja_JP"}
    FANZA = {'age_check_done': '1'}


class Headers:
    """请求头配置"""
    DEFAULT = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    VNDB = {
        'Content-Type': 'application/json',
        'User-Agent': 'ButterFetch/5.2'
    }


class Templates:
    """字符串模板"""
    FOUND_RESULTS = "✅ 找到 {count} 个🧈!"
    FOUND_WITH_SNIFF = "✅ 找到 {count} 个🧈! (含 {sniff_count} 个VNDB嗅探)"
    COPIED_ID = "已复制: {id}"
    LOG_STATUS = "共 {count} 条 | 📊 INFO: {info} | ⚠️ WARN: {warn} | ❌ ERR: {err} | 📁 {size}"
    
    @classmethod
    def format_found(cls, count: int, sniff_count: int = 0) -> str:
        if sniff_count > 0:
            return cls.FOUND_WITH_SNIFF.format(count=count, sniff_count=sniff_count)
        return cls.FOUND_RESULTS.format(count=count)
    
    @classmethod
    def format_log_status(cls, count: int, stats: Dict[str, int], size: str) -> str:
        return cls.LOG_STATUS.format(
            count=count,
            info=stats.get('INFO', 0),
            warn=stats.get('WARNING', 0),
            err=stats.get('ERROR', 0),
            size=size
        )


LOG_LEVEL_COLORS: Dict[str, str] = {
    "INFO": "#2ecc71",
    "WARNING": "#f39c12",
    "ERROR": "#e74c3c",
    "DEBUG": "#3498db",
}

SOURCE_STYLES: Dict[SearchSource, Tuple[str, str, str, str, str]] = {
    SearchSource.DLSITE: ("inverse-success", "success", "🚀 前往 DLsite", "outline-success", "inverse-success"),
    SearchSource.FANZA: ("inverse-danger", "danger", "🚀 前往 FANZA", "outline-danger", "inverse-danger"),
    SearchSource.VNDB: ("inverse-warning", "warning", "🚀 前往 VNDB", "outline-warning", "inverse-warning"),
}

GROUP_STYLES: Dict[str, str] = {
    "🟢 DLsite": "outline-success",
    "🔴 FANZA": "outline-danger",
    "🟣 VNDB": "outline-warning",
}

KAOMOJI_LIST: List[str] = [
    "✨ 呐，今天想玩什么呢？",
    "🐾 (｡･ω･｡) 等待指令中...",
    "🌸 樱花飘落的速度是秒速5厘米...",
    "🎮 找游戏这种事交给我吧！",
    "🔍 让我康康是谁在找黄油...",
    "🐱 喵呜？是在叫我吗？",
    "💜 VNDB 是紫色的哦！"
]


# ============================================================================
# 正则表达式模式
# ============================================================================

class Patterns:
    """正则表达式模式集合"""
    DLSITE_CLEAN = re.compile(r'[【】$$$$$$（）~～！!\s]')
    DLSITE_LINK = re.compile(r'href="(https://www\.dlsite\.com/[^"]+?/product_id/((?:RJ|VJ)\d+)\.html)"')
    FANZA_PREFIX = re.compile(r'^(?:【[^】]+】)?(?:デジタル\|?)?(?:還元)?(?:アダルト)?(?:PC)?(?:ゲーム)?\s*')
    FANZA_ID = re.compile(r'/detail/([a-zA-Z0-9_]+)')
    VNDB_SNIFF_DLSITE = re.compile(r'(?:product_id|/id)/([RV]J\d+)(?:\.html)?', re.IGNORECASE)
    VNDB_SNIFF_DMM = re.compile(r'(?:cid=|/detail/)([a-z0-9_]+?)(?:/|$|\?)', re.IGNORECASE)
    OG_IMAGE = re.compile(r'<meta property="og:image" content="(.*?)"')
    GEOMETRY = re.compile(r'^\d+x\d+(\+\d+\+\d+)?$')
    
    NON_GAME_PATTERNS = [
        re.compile(r'_ost$', re.IGNORECASE),
        re.compile(r'_soundtrack', re.IGNORECASE),
        re.compile(r'_music', re.IGNORECASE),
        re.compile(r'_vocal', re.IGNORECASE),
        re.compile(r'_drama', re.IGNORECASE),
        re.compile(r'_artbook', re.IGNORECASE),
        re.compile(r'_settei', re.IGNORECASE),
    ]
    
    @classmethod
    def is_non_game_id(cls, gid: str) -> bool:
        return any(p.search(gid) for p in cls.NON_GAME_PATTERNS)


# ============================================================================
# 资源管理器
# ============================================================================

class ResourceManager:
    """资源管理器 - 确保所有资源正确清理"""
    
    _instance: Optional['ResourceManager'] = None
    
    def __new__(cls) -> 'ResourceManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cleanups = []
            cls._instance._initialized = False
        return cls._instance
    
    def initialize(self) -> None:
        if not self._initialized:
            atexit.register(self.cleanup_all)
            self._initialized = True
    
    def register(self, cleanup: Callable[[], None], name: str = "") -> None:
        self._cleanups.append((cleanup, name))
        logger.debug(f"注册清理函数: {name or cleanup.__name__}")
    
    def cleanup_all(self) -> None:
        logger.info("开始清理资源...")
        for cleanup, name in reversed(self._cleanups):
            try:
                cleanup()
                logger.debug(f"清理完成: {name or cleanup.__name__}")
            except Exception as e:
                logger.error(f"清理失败 [{name}]: {e}")
        self._cleanups.clear()
        logger.info("资源清理完成")


resource_manager = ResourceManager()
resource_manager.initialize()


# ============================================================================
# 全局异常处理
# ============================================================================

class GlobalExceptionHandler:
    """全局异常处理器"""
    
    _setup_done: bool = False
    
    @classmethod
    def setup(cls, app: Optional[tk.Tk] = None) -> None:
        if cls._setup_done:
            return
        
        def handle_exception(exc_type, exc_value, exc_tb):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_tb)
                return
            
            logger.error(
                "未捕获的异常",
                exc_info=(exc_type, exc_value, exc_tb)
            )
            
            try:
                messagebox.showerror(
                    "发生错误 😿",
                    f"程序遇到了问题喵...\n\n{exc_type.__name__}: {exc_value}"
                )
            except Exception:
                pass
        
        sys.excepthook = handle_exception
        
        if app:
            app.report_callback_exception = lambda *args: handle_exception(*args)
        
        cls._setup_done = True
        logger.info("全局异常处理器已设置")


# ============================================================================
# 配置管理
# ============================================================================

class AppConfig:
    """应用全局配置"""
    
    _config_file = resource_path("butterfetch_config.json")
    
    def __init__(self):
        self._observers: List[Callable[[str, Any], None]] = []
        self._init_defaults()
        self._load()
    
    def _init_defaults(self) -> None:
        self.theme_mode: str = "light"
        self.is_pinned: bool = False
        self.window_geometry: str = "600x980"
    
    def _load(self) -> None:
        try:
            if os.path.exists(self._config_file):
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._validate_and_apply(data)
                logger.info("配置加载成功")
        except Exception as e:
            logger.warning(f"配置加载失败: {e}")
    
    def _validate_and_apply(self, data: dict) -> None:
        theme = data.get('theme_mode', 'light')
        self.theme_mode = theme if theme in ('light', 'dark') else 'light'
        self.is_pinned = bool(data.get('is_pinned', False))
        geometry = data.get('window_geometry', '600x980')
        if Patterns.GEOMETRY.match(geometry):
            self.window_geometry = geometry
        else:
            self.window_geometry = '600x980'
    
    def save(self) -> None:
        try:
            data = {
                'theme_mode': self.theme_mode,
                'is_pinned': self.is_pinned,
                'window_geometry': self.window_geometry
            }
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"配置保存失败: {e}")
    
    def set(self, key: str, value: Any) -> None:
        old_value = getattr(self, key, None)
        setattr(self, key, value)
        if old_value != value:
            for observer in self._observers:
                try:
                    observer(key, value)
                except Exception as e:
                    logger.error(f"配置观察者错误: {e}")
    
    def add_observer(self, callback: Callable[[str, Any], None]) -> None:
        self._observers.append(callback)
    
    @property
    def is_light(self) -> bool:
        return self.theme_mode == "light"
    
    @property
    def bg_color(self) -> str:
        return Colors.LIGHT_BG if self.is_light else Colors.DARK_BG
    
    @property
    def fg_color(self) -> str:
        return Colors.TEXT if self.is_light else "white"
    
    @property
    def theme_name(self) -> str:
        return "cosmo" if self.is_light else "cyborg"


config = AppConfig()


# ============================================================================
# 内存监控
# ============================================================================

class MemoryMonitor:
    """内存监控器"""
    
    def __init__(self, threshold_mb: int = 200):
        self._threshold_bytes = threshold_mb * 1024 * 1024
        self._last_check: float = 0.0
        self._check_interval: int = 30
    
    def should_cleanup(self) -> bool:
        import time
        current_time = time.time()
        
        if current_time - self._last_check < self._check_interval:
            return False
        
        self._last_check = current_time
        
        try:
            import psutil
            usage = psutil.Process(os.getpid()).memory_info().rss
            if usage > self._threshold_bytes:
                logger.warning(f"内存超阈值: {usage / 1024 / 1024:.1f}MB")
                return True
        except ImportError:
            pass
        
        return False


memory_monitor = MemoryMonitor(Limits.MEMORY_THRESHOLD_MB)


# ============================================================================
# 缓存系统
# ============================================================================

class LRUCache:
    """通用 LRU 缓存"""
    
    def __init__(self, max_size: int = 20):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.RLock()
        self._hits: int = 0
        self._misses: int = 0
    
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None
    
    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = value
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)
                self._cache[key] = value
    
    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
    
    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._cache
    
    @property
    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {"size": len(self._cache), "hit_rate": f"{hit_rate:.1f}%"}


class ImageCache(LRUCache):
    """图片缓存"""
    
    def __init__(self, max_size: int = 20):
        super().__init__(max_size)
    
    def clear(self) -> None:
        super().clear()
        gc.collect()
        logger.info("图片缓存已清空")
    
    def cleanup_if_needed(self) -> None:
        if memory_monitor.should_cleanup():
            self.clear()


# ============================================================================
# 网络服务
# ============================================================================

class NetworkService:
    """网络请求服务"""
    
    def __init__(self):
        self._session: Optional[requests.Session] = None
        self._create_session()
    
    def _create_session(self) -> None:
        self._session = requests.Session()
        
        retry = Retry(
            total=Limits.RETRY_TIMES,
            backoff_factor=Limits.RETRY_BACKOFF,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=Limits.POOL_CONNECTIONS,
            pool_maxsize=Limits.POOL_MAXSIZE
        )
        
        self._session.mount('http://', adapter)
        self._session.mount('https://', adapter)
        
        logger.info("网络服务初始化完成")
    
    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._create_session()
        return self._session
    
    def reset_session(self) -> None:
        try:
            if self._session:
                self._session.close()
        except Exception:
            pass
        self._create_session()
        logger.debug("网络连接已重置")
    
    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        for attempt in range(2):
            try:
                if method == 'GET':
                    return self.session.get(url, **kwargs)
                else:
                    return self.session.post(url, **kwargs)
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                if attempt == 0:
                    logger.warning(f"连接错误，重置连接重试... ({e.__class__.__name__})")
                    self.reset_session()
                else:
                    raise
        
        if method == 'GET':
            return self.session.get(url, **kwargs)
        return self.session.post(url, **kwargs)
    
    def get(self, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault('timeout', Timeouts.REQUEST)
        kwargs.setdefault('headers', Headers.DEFAULT)
        return self._request_with_retry('GET', url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault('timeout', Timeouts.REQUEST)
        return self._request_with_retry('POST', url, **kwargs)
    
    def close(self) -> None:
        if self._session:
            self._session.close()
            self._session = None
            logger.info("网络服务已关闭")


network = NetworkService()
resource_manager.register(network.close, "NetworkService")


# ============================================================================
# 日志管理
# ============================================================================

class LogManager:
    """日志管理器"""
    
    def __init__(self, log_file: str):
        self.log_file = log_file
        self._cache: List[str] = []
        self._last_read_pos: int = 0
    
    def read_all(self) -> List[str]:
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    self._cache = f.readlines()
                    self._last_read_pos = f.tell()
                return self._cache
        except Exception as e:
            logger.error(f"读取日志失败: {e}")
        return []
    
    def read_new(self) -> List[str]:
        new_lines = []
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    f.seek(self._last_read_pos)
                    new_lines = f.readlines()
                    self._last_read_pos = f.tell()
                    self._cache.extend(new_lines)
        except Exception as e:
            logger.error(f"增量读取日志失败: {e}")
        return new_lines
    
    def clear(self) -> bool:
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write("")
            self._cache.clear()
            self._last_read_pos = 0
            logger.info("日志已清空")
            return True
        except Exception as e:
            logger.error(f"清空日志失败: {e}")
            return False
    
    def export(self, export_path: str) -> bool:
        try:
            import shutil
            shutil.copy2(self.log_file, export_path)
            logger.info(f"日志已导出到: {export_path}")
            return True
        except Exception as e:
            logger.error(f"导出日志失败: {e}")
            return False
    
    def filter_by_level(self, level: str) -> List[str]:
        if level == "ALL":
            return self._cache
        return [line for line in self._cache if f"[{level}]" in line]
    
    def get_stats(self) -> Dict[str, int]:
        stats = {"INFO": 0, "WARNING": 0, "ERROR": 0, "DEBUG": 0}
        for line in self._cache:
            for level in stats.keys():
                if f"[{level}]" in line:
                    stats[level] += 1
                    break
        return stats
    
    def get_file_size(self) -> str:
        try:
            size = os.path.getsize(self.log_file)
            if size < 1024:
                return f"{size} B"
            elif size < 1024 * 1024:
                return f"{size / 1024:.1f} KB"
            else:
                return f"{size / 1024 / 1024:.1f} MB"
        except Exception:
            return "未知"


# ============================================================================
# 数据模型
# ============================================================================

@dataclass
class SearchResult:
    """搜索结果数据类"""
    source: SearchSource
    id: str
    title: str
    url: str
    thumb_url: str = ""
    from_vndb: bool = False


@dataclass
class SniffedShopInfo:
    """VNDB 嗅探到的商店信息"""
    dlsite_ids: List[str] = field(default_factory=list)
    fanza_ids: List[str] = field(default_factory=list)


@dataclass
class SearchResponse:
    """搜索响应"""
    results: List[SearchResult] = field(default_factory=list)
    error: Optional[str] = None
    source: Optional[SearchSource] = None


@dataclass
class GroupedResults:
    """分组搜索结果"""
    dlsite: List[SearchResult] = field(default_factory=list)
    fanza: List[SearchResult] = field(default_factory=list)
    vndb: List[SearchResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def all(self) -> List[SearchResult]:
        return self.dlsite + self.fanza + self.vndb
    
    def total_count(self) -> int:
        return len(self.dlsite) + len(self.fanza) + len(self.vndb)
    
    def is_empty(self) -> bool:
        return self.total_count() == 0
    
    def sniffed_count(self) -> int:
        return sum(1 for r in self.all() if r.from_vndb)
    
    def group_labels(self) -> List[Tuple[str, int, int, str]]:
        labels = []
        idx = 0
        
        if self.dlsite:
            labels.append(("🟢 DLsite", idx, len(self.dlsite), GROUP_STYLES["🟢 DLsite"]))
            idx += len(self.dlsite)
        
        if self.fanza:
            labels.append(("🔴 FANZA", idx, len(self.fanza), GROUP_STYLES["🔴 FANZA"]))
            idx += len(self.fanza)
        
        if self.vndb:
            labels.append(("🟣 VNDB", idx, len(self.vndb), GROUP_STYLES["🟣 VNDB"]))
        
        return labels


@dataclass 
class Shortcut:
    """快捷键定义"""
    key: str
    description: str
    callback: Callable


# ============================================================================
# 搜索提供者接口
# ============================================================================

class ISearchProvider(ABC):
    """搜索提供者接口"""
    
    @abstractmethod
    def search(self, keyword: str) -> SearchResponse:
        pass
    
    @property
    @abstractmethod
    def source(self) -> SearchSource:
        pass


def safe_search(source: SearchSource):
    """搜索安全装饰器"""
    def decorator(func: Callable[..., List[SearchResult]]):
        @wraps(func)
        def wrapper(*args, **kwargs) -> SearchResponse:
            try:
                results = func(*args, **kwargs)
                return SearchResponse(results=results, source=source)
            except requests.Timeout:
                logger.warning(f"[{source.value}] 请求超时")
                return SearchResponse(error="请求超时", source=source)
            except requests.RequestException as e:
                logger.warning(f"[{source.value}] 网络错误: {e}")
                return SearchResponse(error="网络错误", source=source)
            except Exception as e:
                logger.error(f"[{source.value}] 未知错误: {e}")
                return SearchResponse(error=f"错误: {str(e)[:20]}", source=source)
        return wrapper
    return decorator


# ============================================================================
# 搜索实现
# ============================================================================

class VNDBSearchProvider(ISearchProvider):
    """VNDB 搜索提供者"""
    
    @property
    def source(self) -> SearchSource:
        return SearchSource.VNDB
    
    @safe_search(SearchSource.VNDB)
    def search(self, keyword: str) -> List[SearchResult]:
        results = []
        
        payload = {
            "filters": ["search", "=", keyword],
            "fields": "id, title, titles.title, titles.lang, image.url",
            "results": Limits.MAX_RESULTS
        }
        
        resp = network.post(APIEndpoints.VNDB_API, headers=Headers.VNDB, json=payload)
        data = resp.json()
        
        for item in data.get('results', []):
            gid = item.get('id', '')
            
            final_title = item.get('title', 'Unknown')
            for t_obj in item.get('titles', []):
                if t_obj.get('lang') == 'ja' and t_obj.get('title'):
                    final_title = t_obj['title']
                    break
            
            img_obj = item.get('image')
            thumb_url = img_obj.get('url', '') if img_obj else ""
            
            results.append(SearchResult(
                source=SearchSource.VNDB,
                id=gid,
                title=final_title,
                url=f"https://vndb.org/{gid}",
                thumb_url=thumb_url
            ))
        
        logger.info(f"[VNDB] 找到 {len(results)} 个结果")
        return results


class DLsiteSearchProvider(ISearchProvider):
    """DLsite 搜索提供者"""
    
    @property
    def source(self) -> SearchSource:
        return SearchSource.DLSITE
    
    @safe_search(SearchSource.DLSITE)
    def search(self, keyword: str) -> List[SearchResult]:
        keywords = list(dict.fromkeys([
            keyword,
            Patterns.DLSITE_CLEAN.sub('', keyword)
        ]))
        
        results: List[SearchResult] = []
        seen: Set[str] = set()
        
        for kw in keywords[:2]:
            if len(results) >= Limits.MAX_RESULTS:
                break
            
            for mode in APIEndpoints.DLSITE_MODES:
                if len(results) >= Limits.MAX_RESULTS:
                    break
                
                url = APIEndpoints.dlsite_search(mode, kw)
                resp = network.get(url, cookies=Cookies.DLSITE)
                
                for link, gid in Patterns.DLSITE_LINK.findall(resp.text):
                    if gid in seen:
                        continue
                    
                    title_match = re.search(
                        f'product_id/{gid}.*?title="(.*?)"',
                        resp.text,
                        re.S
                    )
                    title = title_match.group(1).replace('"', '').strip() if title_match else gid
                    
                    results.append(SearchResult(
                        source=SearchSource.DLSITE,
                        id=gid,
                        title=title,
                        url=link
                    ))
                    seen.add(gid)
                    
                    if len(results) >= Limits.MAX_RESULTS:
                        break
        
        logger.info(f"[DLsite] 找到 {len(results)} 个结果")
        return results


class FanzaSearchProvider(ISearchProvider):
    """FANZA 搜索提供者"""
    
    @property
    def source(self) -> SearchSource:
        return SearchSource.FANZA
    
    @safe_search(SearchSource.FANZA)
    def search(self, keyword: str) -> List[SearchResult]:
        results: List[SearchResult] = []
        
        url = APIEndpoints.fanza_search(keyword)
        resp = network.get(url, cookies=Cookies.FANZA)
        
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        items = soup.select('li.tmb-list-item, div.t-item')
        if items:
            links = [item.find('a', href=Patterns.FANZA_ID) for item in items]
        else:
            links = soup.find_all('a', href=Patterns.FANZA_ID)
        
        seen: Set[str] = set()
        
        for link in links:
            if not link:
                continue
            
            match = Patterns.FANZA_ID.search(link.get('href', ''))
            if not match:
                continue
            
            gid = match.group(1)
            raw_title = link.get_text(strip=True)
            
            if not raw_title or gid in seen:
                continue
            
            title = Patterns.FANZA_PREFIX.sub('', raw_title).strip() or raw_title
            
            thumb = ""
            img_tag = link.find_previous('img')
            if img_tag:
                thumb = img_tag.get('src', '')
            
            results.append(SearchResult(
                source=SearchSource.FANZA,
                id=gid,
                title=title,
                url=APIEndpoints.fanza_detail(gid),
                thumb_url=thumb
            ))
            seen.add(gid)
            
            if len(results) >= Limits.MAX_RESULTS:
                break
        
        logger.info(f"[FANZA] 找到 {len(results)} 个结果")
        return results


# ============================================================================
# VNDB 嗅探与 ID 获取
# ============================================================================

def sniff_shop_ids_from_vndb(vndb_results: List[SearchResult]) -> SniffedShopInfo:
    """从 VNDB 结果页面嗅探所有商店 ID"""
    sniffed = SniffedShopInfo()
    dlsite_seen: Set[str] = set()
    fanza_seen: Set[str] = set()
    
    for result in vndb_results:
        try:
            resp = network.get(result.url)
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            for anchor in soup.find_all('a', href=True):
                href = anchor['href']
                
                if 'dlsite.com' in href:
                    for match in Patterns.VNDB_SNIFF_DLSITE.finditer(href):
                        gid = match.group(1).upper()
                        if gid not in dlsite_seen:
                            sniffed.dlsite_ids.append(gid)
                            dlsite_seen.add(gid)
                
                elif 'dmm.co.jp' in href and '/detail/' in href:
                    match = Patterns.VNDB_SNIFF_DMM.search(href)
                    if match:
                        gid = match.group(1)
                        if gid not in fanza_seen and not Patterns.is_non_game_id(gid):
                            sniffed.fanza_ids.append(gid)
                            fanza_seen.add(gid)
        
        except Exception as e:
            logger.warning(f"[VNDB嗅探] 解析 {result.id} 失败: {e}")
    
    logger.info(f"[VNDB嗅探] DLsite: {len(sniffed.dlsite_ids)}个, FANZA: {len(sniffed.fanza_ids)}个")
    return sniffed


def fetch_dlsite_info_by_id(gid: str) -> Optional[SearchResult]:
    """通过 ID 获取 DLsite 游戏信息"""
    try:
        for mode in APIEndpoints.DLSITE_MODES:
            url = APIEndpoints.dlsite_product(mode, gid)
            resp = network.get(url, cookies=Cookies.DLSITE)
            
            if resp.status_code == 200 and gid in resp.text:
                soup = BeautifulSoup(resp.content, 'html.parser')
                
                title_tag = (
                    soup.select_one('#work_name a') or
                    soup.select_one('h1#work_name') or
                    soup.select_one('meta[property="og:title"]')
                )
                
                if title_tag:
                    if title_tag.name == 'meta':
                        title = title_tag.get('content', gid)
                    else:
                        title = title_tag.get_text(strip=True)
                else:
                    title = gid
                
                logger.info(f"[DLsite] 成功获取 {gid}: {title[:30]}")
                return SearchResult(
                    source=SearchSource.DLSITE,
                    id=gid,
                    title=title,
                    url=url,
                    from_vndb=True
                )
        
        logger.warning(f"[DLsite] {gid} 在所有区域都未找到")
    except Exception as e:
        logger.warning(f"[DLsite] 获取 {gid} 信息失败: {e}")
    return None


def fetch_fanza_info_by_id(gid: str) -> Optional[SearchResult]:
    """通过 ID 获取 FANZA 游戏信息"""
    try:
        url = APIEndpoints.fanza_detail(gid)
        resp = network.get(url, cookies=Cookies.FANZA)
        
        if resp.status_code != 200:
            logger.warning(f"[FANZA] {gid} 页面请求失败: {resp.status_code}")
            return None
        
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        title_tag = (
            soup.select_one('h1#title') or
            soup.select_one('h1.productTitle__txt') or
            soup.select_one('meta[property="og:title"]') or
            soup.select_one('title')
        )
        
        if title_tag:
            if title_tag.name == 'meta':
                title = title_tag.get('content', '')
            else:
                title = title_tag.get_text(strip=True)
            
            title = Patterns.FANZA_PREFIX.sub('', title).strip()
            title = re.sub(r'\s*[-|｜].*(?:DMM|FANZA).*$', '', title).strip()
            
            if title:
                logger.info(f"[FANZA] 成功获取 {gid}: {title[:30]}")
                return SearchResult(
                    source=SearchSource.FANZA,
                    id=gid,
                    title=title,
                    url=url,
                    from_vndb=True
                )
        
        logger.warning(f"[FANZA] {gid} 无法解析标题，使用ID作为标题")
        return SearchResult(
            source=SearchSource.FANZA,
            id=gid,
            title=gid,
            url=url,
            from_vndb=True
        )
        
    except Exception as e:
        logger.warning(f"[FANZA] 获取 {gid} 信息失败: {e}")
    return None


# ============================================================================
# 可取消的图片加载器
# ============================================================================

class CancellableImageLoader:
    """可取消的图片加载器"""
    
    def __init__(self):
        self._current_task_id: int = 0
        self._lock = threading.Lock()
    
    def load(
        self,
        result: SearchResult,
        on_success: Callable[[Any], None],
        on_error: Callable[[], None],
        image_fetcher: Callable[[SearchResult], Optional[Any]]
    ) -> None:
        with self._lock:
            self._current_task_id += 1
            task_id = self._current_task_id
        
        def worker():
            tk_img = image_fetcher(result)
            with self._lock:
                if task_id == self._current_task_id:
                    if tk_img:
                        on_success(tk_img)
                    else:
                        on_error()
        
        threading.Thread(target=worker, daemon=True).start()
    
    def cancel_current(self) -> None:
        with self._lock:
            self._current_task_id += 1


# ============================================================================
# 动画管理器
# ============================================================================

class AnimationManager:
    """动画管理器"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self._animations: Dict[str, str] = {}
    
    def cancel(self, name: str) -> None:
        if name in self._animations:
            try:
                self.root.after_cancel(self._animations[name])
            except Exception:
                pass
            del self._animations[name]
    
    def cancel_all(self) -> None:
        for after_id in self._animations.values():
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
        self._animations.clear()
    
    def animate_float_up(
        self,
        widget: tk.Widget,
        name: str,
        start_y: float = 0.88,
        end_y: float = 0.83,
        steps: int = 10,
        interval_ms: int = 30,
        on_complete: Optional[Callable] = None
    ) -> None:
        self.cancel(name)
        step_delta = (start_y - end_y) / steps
        
        def step(current: int):
            if current < steps:
                y = start_y - step_delta * current
                widget.place(relx=0.5, rely=y, anchor="center")
                self._animations[name] = self.root.after(
                    interval_ms,
                    lambda: step(current + 1)
                )
            else:
                if name in self._animations:
                    del self._animations[name]
                if on_complete:
                    on_complete()
        
        step(0)
    
    def animate_fade_out(
        self,
        widget: tk.Widget,
        name: str,
        start_y: float = 0.83,
        steps: int = 8,
        interval_ms: int = 40,
        on_complete: Optional[Callable] = None
    ) -> None:
        self.cancel(name)
        
        def step(current: int):
            if current < steps:
                y = start_y - current * 0.008
                widget.place(relx=0.5, rely=y, anchor="center")
                self._animations[name] = self.root.after(
                    interval_ms,
                    lambda: step(current + 1)
                )
            else:
                widget.place_forget()
                if name in self._animations:
                    del self._animations[name]
                if on_complete:
                    on_complete()
        
        step(0)


# ============================================================================
# 快捷键管理器
# ============================================================================

class ShortcutManager:
    """快捷键管理器"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self._shortcuts: List[Shortcut] = []
    
    def register(self, key: str, description: str, callback: Callable) -> None:
        self._shortcuts.append(Shortcut(key, description, callback))
        self.root.bind(key, lambda e: callback())
    
    def get_help_text(self) -> str:
        lines = ["⌨️ 快捷键列表:", ""]
        for s in self._shortcuts:
            lines.append(f"  {s.key:<15} {s.description}")
        return "\n".join(lines)
    
    def unregister_all(self) -> None:
        for s in self._shortcuts:
            try:
                self.root.unbind(s.key)
            except Exception:
                pass
        self._shortcuts.clear()


# ============================================================================
# 搜索状态管理器
# ============================================================================

class SearchStateManager:
    """搜索状态管理器"""
    
    def __init__(self):
        self._state = SearchState.IDLE
        self._observers: List[Callable[[SearchState, SearchState], None]] = []
    
    @property
    def state(self) -> SearchState:
        return self._state
    
    @state.setter
    def state(self, new_state: SearchState) -> None:
        if self._state != new_state:
            old_state = self._state
            self._state = new_state
            logger.debug(f"搜索状态: {old_state.value} -> {new_state.value}")
            self._notify_observers(old_state, new_state)
    
    def _notify_observers(self, old_state: SearchState, new_state: SearchState) -> None:
        for observer in self._observers:
            try:
                observer(old_state, new_state)
            except Exception as e:
                logger.error(f"状态观察者错误: {e}")
    
    def add_observer(self, callback: Callable[[SearchState, SearchState], None]) -> None:
        self._observers.append(callback)
    
    def is_searching(self) -> bool:
        return self._state == SearchState.SEARCHING


# ============================================================================
# 搜索服务
# ============================================================================

class SearchService:
    """搜索服务层"""
    
    def __init__(self, providers: Optional[List[ISearchProvider]] = None):
        self.providers = providers or [
            DLsiteSearchProvider(),
            FanzaSearchProvider(),
            VNDBSearchProvider(),
        ]
        self.image_cache = ImageCache(Limits.IMAGE_CACHE_SIZE)
        self._search_cache = LRUCache(Limits.SEARCH_CACHE_SIZE)
        self._executor = ThreadPoolExecutor(max_workers=Limits.MAX_WORKERS)
        self._cache_lock = threading.Lock()
    
    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
        logger.info("搜索服务线程池已关闭")
    
    def search_all(self, keyword: str, use_cache: bool = True) -> GroupedResults:
        self.image_cache.cleanup_if_needed()
        
        # 检查缓存
        if use_cache:
            with self._cache_lock:
                cached = self._search_cache.get(keyword)
                if cached:
                    logger.info(f"使用缓存结果: {keyword}")
                    return cached
        
        grouped = GroupedResults()
        
        # 并行搜索
        futures = {
            self._executor.submit(provider.search, keyword): provider.source
            for provider in self.providers
        }
        
        for future in as_completed(futures):
            source = futures[future]
            try:
                response: SearchResponse = future.result()
                if response.error:
                    grouped.errors.append(f"{source.value}: {response.error}")
                else:
                    if source == SearchSource.DLSITE:
                        grouped.dlsite = response.results
                    elif source == SearchSource.FANZA:
                        grouped.fanza = response.results
                    elif source == SearchSource.VNDB:
                        grouped.vndb = response.results
            except Exception as e:
                error_msg = f"{source.value}: {str(e)[:20]}"
                grouped.errors.append(error_msg)
                logger.error(f"搜索失败 - {error_msg}")
        
        # VNDB 嗅探
        if grouped.vndb:
            self._integrate_vndb_sniffed_results(grouped)
        
        # 缓存结果
        with self._cache_lock:
            self._search_cache.set(keyword, grouped)
        
        logger.info(f"搜索完成: 共 {grouped.total_count()} 个结果")
        return grouped
    
    def _integrate_vndb_sniffed_results(self, grouped: GroupedResults) -> None:
        sniffed = sniff_shop_ids_from_vndb(grouped.vndb)
        
        existing_dlsite_ids = {r.id for r in grouped.dlsite}
        existing_fanza_ids = {r.id for r in grouped.fanza}
        
        tasks: List[Tuple[str, str]] = []
        
        for gid in sniffed.dlsite_ids:
            if gid not in existing_dlsite_ids:
                tasks.append(('dlsite', gid))
        
        for gid in sniffed.fanza_ids:
            if gid not in existing_fanza_ids:
                tasks.append(('fanza', gid))
        
        if not tasks:
            return
        
        futures = {}
        for platform, gid in tasks:
            if platform == 'dlsite':
                futures[self._executor.submit(fetch_dlsite_info_by_id, gid)] = ('dlsite', gid)
            else:
                futures[self._executor.submit(fetch_fanza_info_by_id, gid)] = ('fanza', gid)
        
        for future in as_completed(futures):
            platform, gid = futures[future]
            try:
                result = future.result()
                if result:
                    if platform == 'dlsite':
                        grouped.dlsite.append(result)
                    else:
                        grouped.fanza.append(result)
            except Exception as e:
                logger.warning(f"[VNDB嗅探] 获取 {gid} 失败: {e}")
    
    def fetch_image(self, result: SearchResult) -> Optional[Any]:
        img_url = self._get_image_url(result)
        
        if not img_url:
            return None
        
        cached = self.image_cache.get(img_url)
        if cached:
            return cached
        
        try:
            resp = network.get(img_url, timeout=Timeouts.IMAGE)
            pil_img = Image.open(io.BytesIO(resp.content))
            
            height = UISize.IMG_HEIGHT
            width = int(pil_img.size[0] * (height / pil_img.size[1]))
            pil_img = pil_img.resize((width, height), Image.Resampling.LANCZOS)
            pil_img = self._add_corners(pil_img)
            
            tk_img = ImageTk.PhotoImage(pil_img)
            self.image_cache.set(img_url, tk_img)
            
            return tk_img
        except Exception as e:
            logger.warning(f"图片加载失败: {e}")
            return None
    
    def _get_image_url(self, result: SearchResult) -> Optional[str]:
        try:
            if result.source == SearchSource.DLSITE:
                resp = network.get(result.url, cookies=Cookies.DLSITE)
                match = Patterns.OG_IMAGE.search(resp.text)
                if match:
                    raw = match.group(1).strip()
                    return ("https:" + raw) if raw.startswith("//") else raw
            
            elif result.source == SearchSource.FANZA:
                thumb = result.thumb_url
                if thumb and 'ps.jpg' in thumb:
                    candidate = thumb.replace('ps.jpg', 'pl.jpg')
                    return ('https:' + candidate) if candidate.startswith('//') else candidate
                else:
                    resp = network.get(result.url, cookies=Cookies.FANZA)
                    soup = BeautifulSoup(resp.content, 'html.parser')
                    target = soup.select_one('a[name="package-image"]') or soup.select_one('#package-src')
                    if target:
                        img_url = target.get('href') or target.get('src', '')
                        return ('https:' + img_url) if img_url.startswith('//') else img_url
            
            elif result.source == SearchSource.VNDB:
                return result.thumb_url or None
        except Exception as e:
            logger.error(f"获取图片URL失败: {e}")
        return None
    
    @staticmethod
    def _add_corners(im: Image.Image, radius: int = None) -> Image.Image:
        if radius is None:
            radius = UISize.CORNER_RADIUS
        
        try:
            circle = Image.new('L', (radius * 2, radius * 2), 0)
            draw = ImageDraw.Draw(circle)
            draw.ellipse((0, 0, radius * 2 - 1, radius * 2 - 1), fill=255)
            
            alpha = Image.new('L', im.size, 255)
            width, height = im.size
            
            if im.mode != 'RGBA':
                im = im.convert('RGBA')
            
            alpha.paste(circle.crop((0, 0, radius, radius)), (0, 0))
            alpha.paste(circle.crop((0, radius, radius, radius * 2)), (0, height - radius))
            alpha.paste(circle.crop((radius, 0, radius * 2, radius)), (width - radius, 0))
            alpha.paste(circle.crop((radius, radius, radius * 2, radius * 2)), (width - radius, height - radius))
            
            im.putalpha(alpha)
            return im
        except Exception:
            return im
    
    def clear_cache(self) -> None:
        self.image_cache.clear()
        with self._cache_lock:
            self._search_cache.clear()
        logger.info("所有缓存已清空")


search_service = SearchService()
resource_manager.register(search_service.shutdown, "SearchService")


# ============================================================================
# 图片工具
# ============================================================================

def create_placeholder_image(
    width: int = 530,
    height: int = 380,
    theme: str = "light"
) -> Optional[Any]:
    """生成待机猫猫占位图"""
    try:
        bg_color = (255, 248, 250) if theme == "light" else (45, 40, 45)
        img = Image.new('RGB', (width, height), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        border_color = (255, 220, 230) if theme == "light" else (70, 60, 70)
        draw.rectangle([10, 10, width - 10, height - 10], outline=border_color, width=3)
        
        cx, cy = width // 2, height // 2
        cat_color = (200, 210, 230) if theme == "light" else (80, 80, 100)
        
        draw.polygon([(cx - 60, cy - 40), (cx - 90, cy - 110), (cx - 20, cy - 70)], fill=cat_color)
        draw.polygon([(cx + 60, cy - 40), (cx + 90, cy - 110), (cx + 20, cy - 70)], fill=cat_color)
        draw.ellipse((cx - 80, cy - 80, cx + 80, cy + 60), fill=cat_color)
        
        eye_color = (80, 80, 80) if theme == "light" else (200, 200, 200)
        draw.ellipse((cx - 45, cy - 25, cx - 25, cy - 5), fill=eye_color)
        draw.ellipse((cx + 25, cy - 25, cx + 45, cy - 5), fill=eye_color)
        draw.line((cx - 10, cy + 15, cx, cy + 25), fill=eye_color, width=3)
        draw.line((cx, cy + 25, cx + 10, cy + 15), fill=eye_color, width=3)
        
        blush_color = (255, 180, 190)
        draw.ellipse((cx - 60, cy + 5, cx - 40, cy + 20), fill=blush_color)
        draw.ellipse((cx + 40, cy + 5, cx + 60, cy + 20), fill=blush_color)
        
        return ImageTk.PhotoImage(SearchService._add_corners(img))
    except Exception as e:
        logger.error(f"创建占位图失败: {e}")
        return None


# ============================================================================
# UI 构建器
# ============================================================================

class UIBuilder:
    """UI 组件构建器"""
    
    @staticmethod
    def create_toolbar(
        parent: tk.Widget,
        callbacks: Dict[str, Callable],
        is_pinned: bool,
        is_light: bool
    ) -> Tuple[ttk.Frame, Dict[str, ttk.Button]]:
        toolbar = ttk.Frame(parent, padding=(15, 8))
        toolbar.pack(fill=X)
        
        buttons = {}
        
        buttons['log'] = ttk.Button(
            toolbar, text=UIText.LOG_VIEW,
            bootstyle="outline-secondary",
            command=callbacks['toggle_log']
        )
        buttons['log'].pack(side=LEFT)
        
        buttons['theme'] = ttk.Button(
            toolbar,
            text="🌙" if is_light else "☀️",
            bootstyle="link",
            command=callbacks['toggle_theme']
        )
        buttons['theme'].pack(side=RIGHT)
        
        buttons['pin'] = ttk.Button(
            toolbar,
            text="📌 Fixed" if is_pinned else "📌 Sticky",
            bootstyle="solid-info" if is_pinned else "outline-info",
            command=callbacks['toggle_pin']
        )
        buttons['pin'].pack(side=RIGHT, padx=(0, 10))
        
        return toolbar, buttons
    
    @staticmethod
    def create_search_bar(
        parent: tk.Widget,
        callbacks: Dict[str, Callable],
        placeholder: str,
        bg_color: str
    ) -> Tuple[ttk.Frame, Dict[str, Any]]:
        search_frame = ttk.Frame(parent, padding=(25, 10, 25, 0))
        search_frame.pack(fill=X)
        
        components = {}
        
        ttk.Button(
            search_frame, text="📋",
            bootstyle="outline-info",
            width=5,
            command=callbacks['paste']
        ).pack(side=LEFT, padx=(0, 12))
        
        entry_container = ttk.Frame(search_frame)
        entry_container.pack(side=LEFT, fill=X, expand=True)
        
        entry_var = tk.StringVar()
        entry = ttk.Entry(
            entry_container,
            textvariable=entry_var,
            font=("微软雅黑", 14),
            bootstyle="primary"
        )
        entry.pack(side=LEFT, fill=X, expand=True, ipady=8)
        entry.insert(0, placeholder)
        entry.config(foreground=Colors.SKY)
        
        btn_clear = tk.Label(
            entry_container, text="✖",
            font=("Arial", 12),
            bg=bg_color,
            fg=Colors.CLEAR_NORMAL,
            cursor="hand2"
        )
        btn_clear.place(relx=0.94, rely=0.5, anchor="center")
        
        btn_search = ttk.Button(
            search_frame, text="Search ✨",
            bootstyle="primary",
            command=callbacks['search'],
            width=10
        )
        btn_search.pack(side=LEFT, padx=(12, 0))
        
        components['entry_var'] = entry_var
        components['entry'] = entry
        components['btn_clear'] = btn_clear
        components['btn_search'] = btn_search
        
        return search_frame, components
    
    @staticmethod
    def create_result_area(parent: tk.Widget) -> Tuple[ttk.Frame, Dict[str, Any]]:
        combo_frame = ttk.Frame(parent, padding=(25, 5, 25, 10))
        combo_frame.pack(fill=X)
        
        components = {}
        
        components['lbl_tip'] = ttk.Label(
            combo_frame, text=UIText.READY,
            font=("微软雅黑", 10),
            foreground="gray"
        )
        components['lbl_tip'].pack(anchor="w", pady=(5, 3))
        
        components['group_frame'] = ttk.Frame(combo_frame)
        components['group_frame'].pack(fill=X, pady=(0, 5))
        
        components['combo'] = ttk.Combobox(
            combo_frame,
            state="readonly",
            font=("微软雅黑", 13),
            bootstyle="info"
        )
        components['combo'].pack(fill=X)
        components['combo'].set(UIText.WAITING)
        
        return combo_frame, components
    
    @staticmethod
    def create_detail_card(
        parent: tk.Widget,
        callbacks: Dict[str, Callable]
    ) -> Tuple[ttk.Labelframe, Dict[str, Any]]:
        card = ttk.Labelframe(
            parent,
            text=" ✨ Details ",
            padding=15,
            bootstyle="primary"
        )
        card.pack(fill=BOTH, expand=True)
        
        components = {}
        
        components['img_container'] = ttk.Label(card, anchor="center")
        components['img_container'].pack(side=TOP, fill=BOTH, expand=True, pady=5)
        
        bottom_frame = ttk.Frame(card)
        components['bottom_frame'] = bottom_frame
        
        components['btn_go'] = ttk.Button(
            bottom_frame,
            text="🚀 前往详情页",
            state="disabled",
            command=callbacks['open_url'],
            width=30
        )
        components['btn_go'].pack(side=BOTTOM, pady=(15, 0), ipady=5)
        
        components['btn_id'] = ttk.Button(
            bottom_frame, text="",
            command=callbacks['copy_id'],
            bootstyle="outline-info",
            cursor="hand2"
        )
        components['btn_id'].pack(side=BOTTOM, pady=(0, 6), ipadx=8)
        
        components['lbl_title'] = ttk.Label(
            bottom_frame, text="",
            font=("微软雅黑", 16, "bold"),
            anchor="center",
            wraplength=520,
            justify="center",
            cursor="hand2",
            foreground=Colors.TEXT
        )
        components['lbl_title'].pack(side=BOTTOM, pady=10, fill=X)
        
        components['lbl_source'] = ttk.Label(
            bottom_frame, text="",
            font=("Segoe UI", 10, "bold"),
            bootstyle="inverse-secondary",
            anchor="center"
        )
        components['lbl_source'].pack(side=BOTTOM, pady=5)
        
        return card, components


# ============================================================================
# 事件处理器
# ============================================================================

class EventHandlers:
    """事件处理器集合"""
    
    def __init__(self, app: 'ButterFetchApp'):
        self.app = app
    
    def on_entry_focus_in(self, event: tk.Event) -> None:
        if self.app.entry.get() == self.app.placeholder_text:
            self.app.entry.delete(0, "end")
            self.app.entry.config(
                foreground="black" if config.is_light else "white"
            )
            self.app.is_placeholder_active = False
    
    def on_entry_focus_out(self, event: tk.Event) -> None:
        if not self.app.entry.get():
            self.app.placeholder_text = random.choice(KAOMOJI_LIST)
            self.app.entry.insert(0, self.app.placeholder_text)
            self.app.entry.config(foreground=Colors.SKY)
            self.app.is_placeholder_active = True
    
    def on_clear_enter(self, event: tk.Event) -> None:
        self.app.btn_clear.config(fg=Colors.CLEAR_HOVER)
    
    def on_clear_leave(self, event: tk.Event) -> None:
        self.app.btn_clear.config(fg=Colors.CLEAR_NORMAL)
    
    def on_title_enter(self, event: tk.Event) -> None:
        self.app.lbl_title.config(foreground=Colors.SAKURA)
    
    def on_title_leave(self, event: tk.Event) -> None:
        self.app.lbl_title.config(foreground=Colors.TEXT)
    
    def on_combo_select(self, event: Optional[tk.Event]) -> None:
        idx = self.app.combo.current()
        if idx < 0:
            return
        
        self.app.combo.selection_clear()
        self.app.card.focus_set()
        
        current_list = (
            self.app._filtered_results
            if self.app._is_filtered and self.app._filtered_results
            else self.app.all_results
        )
        
        if idx < len(current_list):
            self.app._display_result(current_list[idx])


# ============================================================================
# 主应用窗口
# ============================================================================

class ButterFetchApp(ttk.Window):
    """ButterFetch 主应用窗口"""
    
    def __init__(self):
        super().__init__(themename=config.theme_name)
        self.title("🧈 ButterFetch 🧈 ")
        self.geometry(config.window_geometry)
        
        # 图标引用先初始化
        self._icon_16 = None
        self._icon_32 = None  
        self._icon_48 = None
        
        # 立即设置一次
        self._setup_icon()
        
        # 设置全局异常处理
        GlobalExceptionHandler.setup(self)
        
        # 状态变量
        self.is_pinned: bool = config.is_pinned
        self.current_result: Optional[SearchResult] = None
        self.grouped_results: Optional[GroupedResults] = None
        self.all_results: List[SearchResult] = []
        self.placeholder_text: str = random.choice(KAOMOJI_LIST)
        self.is_placeholder_active: bool = True
        self._search_timer: Optional[str] = None
        self._is_filtered: bool = False
        self._filtered_results: Optional[List[SearchResult]] = None
        
        # 日志视图状态
        self.is_log_view: bool = False
        self._log_view_built: bool = False
        self.log_manager = LogManager(resource_path("butterfetch.log"))
        self._log_refresh_job: Optional[str] = None
        self._log_search_timer: Optional[str] = None
        
        # 管理器
        self.state_manager = SearchStateManager()
        self.animation_manager = AnimationManager(self)
        self.shortcut_manager = ShortcutManager(self)
        self.image_loader = CancellableImageLoader()
        self.event_handlers = EventHandlers(self)
        
        # 初始化 UI
        self._apply_style()
        self._setup_icon()
        self._build_ui()
        self._setup_context_menu()
        self._bind_events()
        self._register_shortcuts()
        self._load_standby_image()
        self._toggle_detail_view(False)
        
        if self.is_pinned:
            self.attributes('-topmost', True)
        
        # 注册状态观察者
        self.state_manager.add_observer(self._on_state_change)
        
        logger.info("ButterFetch 启动成功")
        
        self.after(50, self._setup_icon)
    
    def _apply_style(self) -> None:
        self.style.colors.warning = Colors.GRAPE
        self.style.colors.primary = Colors.SAKURA
        self.style.colors.info = Colors.SKY
        self.style.configure('.', font=('Microsoft YaHei UI', 10))
        self.style.map('TCombobox',
            selectbackground=[('readonly', config.bg_color), ('!readonly', config.bg_color)],
            selectforeground=[('readonly', config.fg_color), ('!readonly', config.fg_color)],
            fieldbackground=[('readonly', config.bg_color), ('!readonly', config.bg_color)]
        )
    
    def _setup_icon(self) -> None:
        """设置窗口图标"""
        icon_path = resource_path("ButterFetch.ico")
        if os.path.exists(icon_path):
            try:
                # 加载图标
                icon_img = Image.open(icon_path)
                
                # 创建多个尺寸并保持引用
                self._icon_16 = ImageTk.PhotoImage(icon_img.resize((16, 16), Image.Resampling.LANCZOS))
                self._icon_32 = ImageTk.PhotoImage(icon_img.resize((32, 32), Image.Resampling.LANCZOS))
                self._icon_48 = ImageTk.PhotoImage(icon_img.resize((48, 48), Image.Resampling.LANCZOS))
                
                # 设置图标
                self.iconphoto(True, self._icon_48, self._icon_32, self._icon_16)
            except Exception as e:
                logger.warning(f"图标加载失败: {e}")

    
    def _build_ui(self) -> None:
        # 工具栏
        callbacks = {
            'toggle_log': self._toggle_log_view,
            'toggle_theme': self._toggle_theme,
            'toggle_pin': self._toggle_pin
        }
        _, toolbar_btns = UIBuilder.create_toolbar(
            self, callbacks, self.is_pinned, config.is_light
        )
        self.btn_log = toolbar_btns['log']
        self.btn_theme = toolbar_btns['theme']
        self.btn_pin = toolbar_btns['pin']
        
        # 搜索栏
        search_callbacks = {
            'paste': self._smart_paste,
            'search': self._request_search
        }
        _, search_comps = UIBuilder.create_search_bar(
            self, search_callbacks, self.placeholder_text, config.bg_color
        )
        self.entry_var = search_comps['entry_var']
        self.entry = search_comps['entry']
        self.btn_clear = search_comps['btn_clear']
        self.btn_search = search_comps['btn_search']
        
        # 进度条
        self.progress_frame = ttk.Frame(self, padding=(25, 5, 25, 0))
        self.progress_frame.pack(fill=X)
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            mode='indeterminate',
            bootstyle="success-striped"
        )
        
        # 结果区域
        _, result_comps = UIBuilder.create_result_area(self)
        self.lbl_tip = result_comps['lbl_tip']
        self.group_button_frame = result_comps['group_frame']
        self.combo = result_comps['combo']
        
        # 卡片容器
        self.card_wrapper = ttk.Frame(self, padding=(20, 10))
        self.card_wrapper.pack(fill=BOTH, expand=True)
        
        # 详情卡片
        detail_callbacks = {
            'open_url': self._open_url,
            'copy_id': self._copy_id
        }
        self.card, detail_comps = UIBuilder.create_detail_card(
            self.card_wrapper, detail_callbacks
        )
        self.img_container = detail_comps['img_container']
        self.bottom_frame = detail_comps['bottom_frame']
        self.btn_go = detail_comps['btn_go']
        self.btn_id = detail_comps['btn_id']
        self.lbl_title = detail_comps['lbl_title']
        self.lbl_source = detail_comps['lbl_source']
        
        # 日志视图框架（延迟构建）
        self.log_frame = ttk.Labelframe(
            self.card_wrapper,
            text=" 📜 运行日志 ",
            padding=10,
            bootstyle="secondary"
        )
        
        # Toast
        self.lbl_toast = ttk.Label(
            self, text="",
            bootstyle="inverse-success",
            padding=10
        )
    
    def _build_log_view(self) -> None:
        """构建日志视图（懒加载）"""
        if self._log_view_built:
            return
        
        # 顶部工具栏
        log_toolbar = ttk.Frame(self.log_frame)
        log_toolbar.pack(fill=X, pady=(0, 10))
        
        
        ttk.Label(log_toolbar, text="级别:").pack(side=LEFT, padx=(15, 5))
        self.log_level_combo = ttk.Combobox(
            log_toolbar,
            values=["ALL", "INFO", "WARNING", "ERROR", "DEBUG"],
            state="readonly",
            width=8
        )
        self.log_level_combo.set("ALL")
        self.log_level_combo.pack(side=LEFT)
        self.log_level_combo.bind("<<ComboboxSelected>>", self._on_log_filter_change)
        
        ttk.Label(log_toolbar, text="搜索:").pack(side=LEFT, padx=(10, 5))
        self.log_search_var = tk.StringVar()
        self.log_search_entry = ttk.Entry(
            log_toolbar,
            textvariable=self.log_search_var,
            width=12
        )
        self.log_search_entry.pack(side=LEFT)
        self.log_search_entry.bind("<KeyRelease>", self._on_log_search)
        
        ttk.Button(
            log_toolbar, text="💾 导出",
            bootstyle="outline-success",
            command=self._export_log
        ).pack(side=RIGHT)
        
        # 日志文本区域
        text_frame = ttk.Frame(self.log_frame)
        text_frame.pack(fill=BOTH, expand=True)
        
        v_scroll = ttk.Scrollbar(text_frame, orient=VERTICAL)
        v_scroll.pack(side=RIGHT, fill=Y)
        
        self.log_text = tk.Text(
            text_frame,
            wrap="none",
            font=("Consolas", 9),
            bg="#1e1e1e" if not config.is_light else "#fafafa",
            fg="#d4d4d4" if not config.is_light else "#333333",
            state="disabled",
            padx=10,
            pady=10,
            yscrollcommand=v_scroll.set
        )
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        v_scroll.config(command=self.log_text.yview)
        
        for level, color in LOG_LEVEL_COLORS.items():
            self.log_text.tag_configure(level, foreground=color)
        
        # 底部状态栏
        bottom_frame = ttk.Frame(self.log_frame)
        bottom_frame.pack(fill=X, pady=(8, 0))
        
        self.log_status = ttk.Label(
            bottom_frame, text="",
            font=("微软雅黑", 9),
            foreground="gray"
        )
        self.log_status.pack(side=LEFT, fill=X, expand=True)
        
        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(side=RIGHT)
        
        ttk.Button(
            btn_frame, text="🔄 刷新",
            bootstyle="outline-primary",
            command=self._refresh_log,
            width=8
        ).pack(side=LEFT, padx=(0, 5))
        
        ttk.Button(
            btn_frame, text="🗑️ 清空",
            bootstyle="outline-danger",
            command=self._quick_clear_log,
            width=8
        ).pack(side=LEFT)
        
        self._log_view_built = True
    
    def _setup_context_menu(self) -> None:
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="📋 复制标题", command=self._copy_title)
        self.context_menu.add_command(label="🆔 复制ID", command=self._copy_id)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🚀 打开链接", command=self._open_url)
        
        self.lbl_title.bind("<Button-3>", self._show_context_menu)
        self.img_container.bind("<Button-3>", self._show_context_menu)
    
    def _show_context_menu(self, event: tk.Event) -> None:
        if self.current_result:
            self.context_menu.post(event.x_root, event.y_root)
    
    def _bind_events(self) -> None:
        # 搜索
        self.entry.bind('<Return>', lambda e: self._request_search())
        self.entry.bind('<FocusIn>', self.event_handlers.on_entry_focus_in)
        self.entry.bind('<FocusOut>', self.event_handlers.on_entry_focus_out)
        
        # 清除按钮
        self.btn_clear.bind("<Button-1>", lambda e: self._clear_entry())
        self.btn_clear.bind("<Enter>", self.event_handlers.on_clear_enter)
        self.btn_clear.bind("<Leave>", self.event_handlers.on_clear_leave)
        
        # 下拉框
        self.combo.bind("<<ComboboxSelected>>", self.event_handlers.on_combo_select)
        
        # 标题
        self.lbl_title.bind("<Enter>", self.event_handlers.on_title_enter)
        self.lbl_title.bind("<Leave>", self.event_handlers.on_title_leave)
        self.lbl_title.bind("<Button-1>", lambda e: self._copy_title())
        
        # 窗口关闭
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _register_shortcuts(self) -> None:
        self.shortcut_manager.register('<Up>', '上一个结果', lambda: self._navigate_result(-1))
        self.shortcut_manager.register('<Down>', '下一个结果', lambda: self._navigate_result(1))
        self.shortcut_manager.register('<Control-v>', '智能粘贴', self._smart_paste)
        self.shortcut_manager.register('<Control-V>', '智能粘贴', self._smart_paste)
        self.shortcut_manager.register('<Escape>', '清空搜索框', self._clear_entry)
    
    def _on_state_change(self, old_state: SearchState, new_state: SearchState) -> None:
        """搜索状态变更回调"""
        if new_state == SearchState.SEARCHING:
            self.btn_search.config(state="disabled")
        else:
            self.btn_search.config(state="normal")
    
    def _on_close(self) -> None:
        self._stop_log_auto_refresh()
        self.animation_manager.cancel_all()
        self.shortcut_manager.unregister_all()
        config.window_geometry = self.geometry()
        config.save()
        logger.info("ButterFetch 关闭")
        self.destroy()
    
    def _toggle_detail_view(self, show: bool) -> None:
        if show:
            self.bottom_frame.pack(side=BOTTOM, fill=X)
        else:
            self.bottom_frame.pack_forget()
    
    def _load_standby_image(self) -> None:
        self.standby_image = create_placeholder_image(theme=config.theme_mode)
        if self.standby_image:
            self.img_container.config(image=self.standby_image)
    
    # ========================================================================
    # 主题与置顶
    # ========================================================================
    
    def _toggle_theme(self) -> None:
        if config.is_light:
            self.style.theme_use("cyborg")
            config.theme_mode = "dark"
            self.btn_theme.config(text="☀️")
            self.btn_clear.config(bg=Colors.DARK_BG)
            if not self.is_placeholder_active:
                self.entry.config(foreground="white")
            if self._log_view_built:
                self.log_text.config(bg="#1e1e1e", fg="#d4d4d4")
        else:
            self.style.theme_use("cosmo")
            config.theme_mode = "light"
            self.btn_theme.config(text="🌙")
            self.btn_clear.config(bg=Colors.LIGHT_BG)
            if not self.is_placeholder_active:
                self.entry.config(foreground="black")
            if self._log_view_built:
                self.log_text.config(bg="#fafafa", fg="#333333")
        
        self._apply_style()
        if not self.all_results and not self.is_log_view:
            self._load_standby_image()
        config.save()
    
    def _toggle_pin(self) -> None:
        self.is_pinned = not self.is_pinned
        config.is_pinned = self.is_pinned
        self.attributes('-topmost', self.is_pinned)
        self.btn_pin.config(
            text="📌 Fixed" if self.is_pinned else "📌 Sticky",
            bootstyle="solid-info" if self.is_pinned else "outline-info"
        )
        config.save()
    
    # ========================================================================
    # 日志视图
    # ========================================================================
    
    def _toggle_log_view(self) -> None:
        self.is_log_view = not self.is_log_view
        if self.is_log_view:
            if not self._log_view_built:
                self._build_log_view()
            self.btn_log.config(text=UIText.LOG_BACK, bootstyle="solid-secondary")
            self.card.pack_forget()
            self.log_frame.pack(fill=BOTH, expand=True)
            self._refresh_log()
            self._start_log_auto_refresh()
        else:
            self.btn_log.config(text=UIText.LOG_VIEW, bootstyle="outline-secondary")
            self.log_frame.pack_forget()
            self.card.pack(fill=BOTH, expand=True)
            self._stop_log_auto_refresh()
    
    def _refresh_log(self) -> None:
        lines = self.log_manager.read_all()
        
        level_filter = self.log_level_combo.get()
        if level_filter != "ALL":
            lines = self.log_manager.filter_by_level(level_filter)
        
        search_keyword = self.log_search_var.get().strip()
        if search_keyword:
            lines = [l for l in lines if search_keyword.lower() in l.lower()]
        
        self._display_log_lines(lines)
    
    def _display_log_lines(self, lines: List[str]) -> None:
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        
        if not lines:
            self.log_text.insert("end", UIText.LOG_EMPTY)
            self._update_log_status(0)
        else:
            for line in lines:
                tag = None
                for level in LOG_LEVEL_COLORS.keys():
                    if f"[{level}]" in line:
                        tag = level
                        break
                if tag:
                    self.log_text.insert("end", line, tag)
                else:
                    self.log_text.insert("end", line)
            
            self._update_log_status(len(lines))
            self.log_text.see("end")
        
        self.log_text.config(state="disabled")
    
    def _update_log_status(self, count: int) -> None:
        stats = self.log_manager.get_stats()
        file_size = self.log_manager.get_file_size()
        self.log_status.config(
            text=Templates.format_log_status(count, stats, file_size)
        )
    
    def _on_log_filter_change(self, event: Optional[tk.Event]) -> None:
        self._refresh_log()
    
    def _on_log_search(self, event: tk.Event) -> None:
        if self._log_search_timer:
            self.after_cancel(self._log_search_timer)
        self._log_search_timer = self.after(300, self._refresh_log)
    
    def _quick_clear_log(self) -> None:
        if self.log_manager.clear():
            self._refresh_log()
            self._show_toast("⚡ 日志已清空喵~", "inverse-danger")
    
    def _export_log(self) -> None:
        default_name = f"butterfetch_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[
                ("日志文件", "*.log"),
                ("文本文件", "*.txt"),
                ("所有文件", "*.*")
            ],
            initialfile=default_name,
            title="导出日志"
        )
        if file_path:
            if self.log_manager.export(file_path):
                self._show_toast("日志已导出喵~", "inverse-success")
            else:
                self._show_toast("导出失败了喵...", "inverse-danger")
    
    def _start_log_auto_refresh(self) -> None:
        def auto_refresh():
            if self.is_log_view:
                new_lines = self.log_manager.read_new()
                if new_lines:
                    self._refresh_log()
                self._log_refresh_job = self.after(
                    Timeouts.LOG_REFRESH_MS,
                    auto_refresh
                )
        self._log_refresh_job = self.after(Timeouts.LOG_REFRESH_MS, auto_refresh)
    
    def _stop_log_auto_refresh(self) -> None:
        if self._log_refresh_job:
            self.after_cancel(self._log_refresh_job)
            self._log_refresh_job = None
    
    # ========================================================================
    # 搜索功能
    # ========================================================================
    
    def _request_search(self) -> None:
        if self._search_timer:
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(Timeouts.DEBOUNCE_MS, self._do_search)
    
    def _do_search(self) -> None:
        keyword = self.entry.get().strip()
        if not keyword or keyword == self.placeholder_text:
            return
        
        if self.state_manager.is_searching():
            return
        
        if self.is_log_view:
            self._toggle_log_view()
        
        self.state_manager.state = SearchState.SEARCHING
        
        # 更新 UI
        self.img_container.config(image='', text=UIText.LOADING)
        self.lbl_tip.config(text=UIText.SEARCHING, foreground=Colors.SKY)
        self.combo.set(UIText.SEARCHING_CAT)
        
        for widget in self.group_button_frame.winfo_children():
            widget.destroy()
        
        self.progress_bar.pack(fill=X, pady=(5, 0))
        self.progress_bar.start(10)
        
        self.card.focus_set()
        self._toggle_detail_view(False)
        
        self._is_filtered = False
        self._filtered_results = None
        
        threading.Thread(
            target=self._search_thread,
            args=(keyword,),
            daemon=True
        ).start()
    
    def _search_thread(self, keyword: str) -> None:
        grouped = search_service.search_all(keyword)
        self.after(0, lambda: self._update_results(grouped))
    
    def _update_results(self, grouped: GroupedResults) -> None:
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        
        self.img_container.config(text="")
        
        self.grouped_results = grouped
        self.all_results = grouped.all()
        
        if grouped.is_empty():
            self.state_manager.state = SearchState.NO_RESULT
            self.combo['values'] = []
            self.combo.set(UIText.NO_RESULT)
            
            if grouped.errors:
                self.lbl_tip.config(
                    text=f"⚠️ {'; '.join(grouped.errors)[:40]}",
                    foreground="orange"
                )
            else:
                self.lbl_tip.config(text=UIText.NOT_FOUND, foreground=Colors.SAKURA)
            
            self._load_standby_image()
            self._toggle_detail_view(False)
            return
        
        self.state_manager.state = SearchState.SUCCESS
        
        self._build_group_buttons(grouped)
        
        self.lbl_tip.config(
            text=Templates.format_found(grouped.total_count(), grouped.sniffed_count()),
            foreground="green"
        )
        
        self.combo['values'] = [self._format_combo_item(r) for r in self.all_results]
        self.combo.current(0)
        self.event_handlers.on_combo_select(None)
    
    def _format_combo_item(self, result: SearchResult) -> str:
        prefix = f"【{result.source.value}】"
        if result.from_vndb:
            prefix = f"【{result.source.value}★】"
        return f"{prefix} {result.title}"
    
    def _build_group_buttons(self, grouped: GroupedResults) -> None:
        for widget in self.group_button_frame.winfo_children():
            widget.destroy()
        
        for label_text, start_idx, count, btn_style in grouped.group_labels():
            btn = ttk.Button(
                self.group_button_frame,
                text=f"{label_text} ({count})",
                bootstyle=btn_style,
                command=lambda s=start_idx, e=start_idx + count: self._filter_by_group(s, e)
            )
            btn.pack(side=LEFT, padx=(0, 5))
        
        btn_all = ttk.Button(
            self.group_button_frame,
            text=f"📋 全部 ({grouped.total_count()})",
            bootstyle="outline-info",
            command=self._show_all_results
        )
        btn_all.pack(side=LEFT, padx=(10, 0))
    
    def _filter_by_group(self, start_idx: int, end_idx: int) -> None:
        if not self.grouped_results:
            return
        
        self._filtered_results = self.all_results[start_idx:end_idx]
        self._is_filtered = True
        
        self.combo['values'] = [
            self._format_combo_item(r) for r in self._filtered_results
        ]
        
        if self._filtered_results:
            self.combo.current(0)
            self._display_result(self._filtered_results[0])
    
    def _show_all_results(self) -> None:
        if not self.grouped_results:
            return
        
        self._is_filtered = False
        self._filtered_results = None
        
        self.combo['values'] = [
            self._format_combo_item(r) for r in self.all_results
        ]
        
        if self.all_results:
            self.combo.current(0)
            self._display_result(self.all_results[0])
    
    def _display_result(self, result: SearchResult) -> None:
        self.current_result = result
        self._toggle_detail_view(True)
        
        self.lbl_title.config(text=result.title)
        
        id_text = f"🆔 {result.id}"
        if result.from_vndb:
            id_text = f"🆔 {result.id} ⭐"
        self.btn_id.config(text=id_text)
        
        if result.source in SOURCE_STYLES:
            label_style, btn_style, btn_text, id_style, _ = SOURCE_STYLES[result.source]
            self.lbl_source.config(text=result.source.value, bootstyle=label_style)
            self.btn_go.config(state="normal", bootstyle=btn_style, text=btn_text)
            self.btn_id.config(bootstyle=id_style)
        
        self.img_container.config(image='', text=UIText.LOADING)
        
        # 使用可取消的图片加载器
        self.image_loader.load(
            result,
            on_success=lambda img: self.after(0, lambda: self._update_image(img)),
            on_error=lambda: self.after(
                0,
                lambda: self.img_container.config(text=UIText.IMAGE_FAILED, image='')
            ),
            image_fetcher=search_service.fetch_image
        )
    
    def _update_image(self, tk_img: Any) -> None:
        self.img_container.config(image=tk_img, text="")
        self.img_container.image = tk_img
    
    # ========================================================================
    # 输入框处理
    # ========================================================================
    
    def _clear_entry(self) -> None:
        self.entry.delete(0, 'end')
        self.is_placeholder_active = False
        self.entry.config(foreground=config.fg_color)
        self.entry.focus_set()
    
    def _smart_paste(self) -> None:
        try:
            text = self.clipboard_get().strip()
            if text:
                self.event_handlers.on_entry_focus_in(None)
                self.entry_var.set(text)
                self._request_search()
        except tk.TclError:
            pass
    
    def _navigate_result(self, delta: int) -> None:
        current_list = (
            self._filtered_results
            if self._is_filtered and self._filtered_results
            else self.all_results
        )
        if not current_list:
            return
        
        idx = self.combo.current() + delta
        if 0 <= idx < len(current_list):
            self.combo.current(idx)
            self._display_result(current_list[idx])
    
    # ========================================================================
    # 操作功能
    # ========================================================================
    
    def _open_url(self) -> None:
        if self.current_result:
            webbrowser.open(self.current_result.url)
    
    def _get_toast_style_for_source(self) -> str:
        if self.current_result and self.current_result.source in SOURCE_STYLES:
            return SOURCE_STYLES[self.current_result.source][4]
        return "inverse-info"
    
    def _copy_id(self) -> None:
        if self.current_result:
            self.clipboard_clear()
            self.clipboard_append(self.current_result.id)
            self._show_toast(
                Templates.COPIED_ID.format(id=self.current_result.id),
                self._get_toast_style_for_source()
            )
    
    def _copy_title(self) -> None:
        if self.current_result:
            self.clipboard_clear()
            self.clipboard_append(self.current_result.title)
            self._show_toast(UIText.TITLE_COPIED, self._get_toast_style_for_source())
    
    def _show_toast(self, text: str, style: str = "inverse-success") -> None:
        self.lbl_toast.config(text=text, bootstyle=style)
        self.lbl_toast.place(relx=0.5, rely=0.88, anchor="center")
        
        self.animation_manager.animate_float_up(
            self.lbl_toast,
            "toast_up",
            start_y=0.88,
            end_y=0.83,
            steps=10,
            interval_ms=30,
            on_complete=lambda: self.after(
                Timeouts.TOAST_DURATION_MS,
                lambda: self.animation_manager.animate_fade_out(
                    self.lbl_toast,
                    "toast_fade",
                    start_y=0.83
                )
            )
        )


# ============================================================================
# 程序入口
# ============================================================================

if __name__ == "__main__":
    app = ButterFetchApp()
    app.mainloop()

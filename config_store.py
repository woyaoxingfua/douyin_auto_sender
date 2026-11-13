"""统一配置存储：单例模式，消除多模块重复读取 config.json 的 DRY 问题。

设计要点：
1. 单例实例，配置只加载一次，内存中缓存
2. 支持环境变量覆盖（优先级：环境变量 > config.json）
3. 提供类型安全的 getter 方法
4. 配置变更通知（回调机制）
5. 统一的配置验证与默认值
6. 向后兼容：保留 config_utils 的导出，逐步迁移
"""
import json
import os
import threading
from typing import Dict, List, Optional, Callable

from config_utils import (
    project_path,
    normalize_config,
    validate_runtime_config,
    normalize_friend,
    COMMON_CITIES,
    search_city_by_name,
    create_default_friend_template,
)


class ConfigStore:
    _instance = None
    _lock = threading.Lock()

    DEFAULT_CONFIG = {
        "api_host": "",
        "api_key": "",
        "message_template": (
            "Hi {nickname}，你所在的{city_name}今天白天{text_day}，晚上{text_night}。\n"
            "气温是{temp_min}到{temp_max}℃，{wind_dir}{wind_scale}级。"
        ),
        "use_local_ocr": True,
        "ocr_api_key": "",
        "ocr_secret_key": "",
        "enter_private_msg_mode": "auto",
        "scroll_amount": -3,
        "send_button_mode": "image",
        "exit_session_mode": "auto",
        "log_level": "DEBUG",
        "schedule_time": "08:00",
        "scheduler_enabled": True,
        "process_monitor": {
            "enabled": True,
            "max_memory_mb": 500,
            "max_cpu_percent": 80,
            "check_interval_sec": 30,
        },
        "ui_regions": {},
        "ocr_texts": {
            "ocr_text_sixin": "消息",
            "ocr_text_send": "发送",
            "ocr_text_exit": "退出会话",
        },
        "friends": [],
    }

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._config: Dict = {}
        self._normalized: Dict = {}
        self._callbacks: List[Callable[[Dict], None]] = []
        self._loaded = False
        self._load_error: Optional[str] = None
        # 磁盘上的原始配置（不含环境变量覆盖），save() 时用于还原
        self._disk_config: Dict = {}
        # 被环境变量覆盖的键 -> 环境变量值
        self._env_applied: Dict = {}

    def _load_from_disk(self):
        cfg_path = project_path("config.json")
        if not os.path.exists(cfg_path):
            self._config = dict(self.DEFAULT_CONFIG)
            self._disk_config = {}
            return

        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self._disk_config = dict(loaded)
            self._config = {**self.DEFAULT_CONFIG, **loaded}
        except json.JSONDecodeError as e:
            self._load_error = f"配置文件不是合法 JSON: {e}"
            self._config = dict(self.DEFAULT_CONFIG)
            self._disk_config = {}

    def _apply_env_overrides(self):
        env_mapping = {
            "DOUYIN_WEATHER_API_KEY": "api_key",
            "BAIDU_OCR_API_KEY": "ocr_api_key",
            "BAIDU_OCR_SECRET_KEY": "ocr_secret_key",
        }
        self._env_applied = {}
        for env_key, cfg_key in env_mapping.items():
            env_value = os.environ.get(env_key)
            if env_value:
                self._config[cfg_key] = env_value.strip()
                self._env_applied[cfg_key] = env_value.strip()

    def load(self):
        if self._loaded:
            return self._config

        self._load_from_disk()
        self._apply_env_overrides()
        self._normalized, _ = normalize_config(self._config)
        self._loaded = True
        return self._config

    def reload(self):
        self._loaded = False
        self._load_error = None
        config = self.load()
        self._notify_callbacks(config)
        return config

    def add_callback(self, callback: Callable[[Dict], None]):
        self._callbacks.append(callback)

    def _notify_callbacks(self, config: Dict):
        for cb in self._callbacks:
            try:
                cb(config)
            except Exception:
                pass

    def get(self, key: str = None, default=None):
        config = self.load()
        if key is None:
            return config
        return config.get(key, default)

    def get_all(self) -> Dict:
        """获取完整配置字典"""
        return self.load()

    def get_api_host(self) -> str:
        return self._normalized.get("api_host", "")

    def get_api_key(self) -> str:
        return self._normalized.get("api_key", "")

    def get_message_template(self) -> str:
        return self._normalized.get("message_template", "")

    def get_use_local_ocr(self) -> bool:
        return self._normalized.get("use_local_ocr", True)

    def get_ocr_api_key(self) -> str:
        return self._normalized.get("ocr_api_key", "")

    def get_ocr_secret_key(self) -> str:
        return self._normalized.get("ocr_secret_key", "")

    def get_friends(self) -> List[Dict]:
        return self._normalized.get("friends", [])

    def get_ui_regions(self) -> Dict:
        return self.load().get("ui_regions", {})

    def get_ocr_texts(self) -> Dict:
        return self.load().get("ocr_texts", {
            "ocr_text_sixin": "消息",
            "ocr_text_send": "发送",
            "ocr_text_exit": "退出会话",
        })

    def get_schedule_time(self) -> str:
        return self.load().get("schedule_time", "08:00")

    def get_scheduler_enabled(self) -> bool:
        return self.load().get("scheduler_enabled", True)

    def get_process_monitor_config(self) -> Dict:
        return self.load().get("process_monitor", {})

    def get_enter_private_msg_mode(self) -> str:
        return self.load().get("enter_private_msg_mode", "auto")

    def get_scroll_amount(self) -> int:
        value = self.load().get("scroll_amount", -3)
        try:
            return int(value)
        except (TypeError, ValueError):
            return -3

    def get_send_button_mode(self) -> str:
        return self.load().get("send_button_mode", "image")

    def get_exit_session_mode(self) -> str:
        return self.load().get("exit_session_mode", "auto")

    def get_log_level(self) -> str:
        return self.load().get("log_level", "INFO")

    def apply_log_level(self):
        """根据配置设置 logging 级别"""
        import logging
        level_name = self.get_log_level()
        level = getattr(logging, level_name.upper(), logging.INFO)
        logging.getLogger().setLevel(level)
        for handler in logging.getLogger().handlers:
            handler.setLevel(level)

    def validate(self) -> List[str]:
        return validate_runtime_config(self._normalized)

    def save(self, config_data: Dict):
        """保存配置到磁盘。

        两个保护：
        1. 以磁盘现有配置为基底合并，避免调用方只传部分键时把
           friends / ui_regions 等未提供的键重置成默认值（丢数据）。
        2. 环境变量覆盖的键（api_key 等）不回写磁盘：调用方拿到的
           config 里带着环境变量的值，直接落盘会把密钥明文持久化。
        """
        cfg_path = project_path("config.json")
        merged = {**self.DEFAULT_CONFIG, **self._disk_config, **config_data}
        for key, env_value in self._env_applied.items():
            if merged.get(key) == env_value:
                # 调用方没有显式改这个键，写回磁盘上的原值
                merged[key] = self._disk_config.get(key, self.DEFAULT_CONFIG.get(key, ""))
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        self.reload()

    def update(self, updates: Dict):
        current = self.load()
        current.update(updates)
        self.save(current)


config_store = ConfigStore()


def get_config() -> Dict:
    return config_store.load()


def get_friends() -> List[Dict]:
    return config_store.get_friends()


def get_api_host() -> str:
    return config_store.get_api_host()


def get_api_key() -> str:
    return config_store.get_api_key()

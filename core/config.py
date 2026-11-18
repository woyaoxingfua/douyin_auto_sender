"""统一配置模块（v7 重写后的唯一配置入口）。

合并了原 config_store.py + config_utils.py 双份实现：
  - ConfigStore 单例：load/reload/save/env 覆盖/回调/类型化 getter
  - 纯函数区：project_path / normalize / validate / 城市速查（原 config_utils）

设计要点：
1. 单例实例，配置只加载一次，内存中缓存
2. 环境变量覆盖（优先级：环境变量 > config.json），且覆盖值不回写磁盘
3. save() 以磁盘现有配置为基底合并，部分保存不丢数据
"""
import json
import os
import threading
from typing import Dict, List, Optional, Callable, Tuple

# ─── 路径 ───

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def project_path(*parts: str) -> str:
    """项目根目录相对路径 -> 绝对路径。"""
    return os.path.join(BASE_DIR, *[str(p) for p in parts])


# ─── 默认模板与城市速查（原 config_utils） ───

DEFAULT_MESSAGE_TEMPLATE = (
    "Hi {nickname}，你所在的{city_name}今天白天{text_day}，晚上{text_night}。\n"
    "气温是{temp_min}到{temp_max}℃，{wind_dir}{wind_scale}级。"
)

COMMON_CITIES = [
    ("北京", "101010100"),
    ("上海", "101020100"),
    ("广州", "101280101"),
    ("深圳", "101280601"),
    ("杭州", "101210101"),
    ("南京", "101190101"),
    ("苏州", "101190401"),
    ("成都", "101270101"),
    ("重庆", "101040100"),
    ("武汉", "101200101"),
    ("西安", "101110101"),
    ("天津", "101030100"),
    ("青岛", "101120201"),
    ("厦门", "101230201"),
    ("长沙", "101250101"),
    ("郑州", "101180101"),
    ("济南", "101120101"),
    ("沈阳", "101070101"),
    ("大连", "101070201"),
    ("哈尔滨", "101050101"),
    ("昆明", "101290101"),
    ("三亚", "101310201"),
    ("拉萨", "101140101"),
    ("乌鲁木齐", "101130101"),
    ("兰州", "101160101"),
]


def search_city_by_name(name: str) -> List[Tuple[str, str]]:
    """在城市速查表中搜索（用户输入后可下拉选择）。"""
    if not name:
        return COMMON_CITIES[:10]
    name = name.strip().lower()
    return [(c, cid) for c, cid in COMMON_CITIES if name in c][:20]


def create_default_friend_template(nickname: str = "示例好友",
                                   city_name: str = "北京") -> Dict:
    """生成一个开箱即用的好友模板。"""
    location_id = next((cid for c, cid in COMMON_CITIES if c == city_name),
                       "101010100")
    return {
        "nickname": nickname,
        "city_name": city_name,
        "location_id": location_id,
        # 保留旧版 city 字段，兼容旧分支读取
        "city": location_id,
        "avatar_image": "",
        "avatar_text": "",
    }


# ─── 归一化与校验（原 config_utils） ───

def _strip_host(host: str) -> str:
    host = (host or "").strip()
    if host.startswith("http://"):
        host = host[len("http://"):]
    if host.startswith("https://"):
        host = host[len("https://"):]
    return host.rstrip("/")


def load_raw(config_path: Optional[str] = None) -> Dict:
    """读原始 config.json（不套默认值；文件不存在返回 {}）。"""
    path = config_path or project_path("config.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_friend(raw_friend: Dict) -> Dict:
    nickname = str(raw_friend.get("nickname", "")).strip()
    location_id = str(raw_friend.get("location_id") or raw_friend.get("city") or "").strip()
    city_name = str(raw_friend.get("city_name", "")).strip()
    avatar_image = str(raw_friend.get("avatar_image", "")).strip().replace("\\", "/")
    avatar_text = str(raw_friend.get("avatar_text", "")).strip()

    if not nickname:
        raise ValueError("nickname 为空，已跳过")
    if not location_id:
        raise ValueError(f"{nickname} 缺少 location_id/city，已跳过")

    return {
        "nickname": nickname,
        "city_name": city_name or f"ID:{location_id}",
        "location_id": location_id,
        "city": location_id,
        "avatar_image": avatar_image,
        "avatar_text": avatar_text,
    }


def normalize_config(raw_config: Dict) -> Tuple[Dict, List[str]]:
    warnings: List[str] = []
    friends: List[Dict] = []
    for index, raw_friend in enumerate(raw_config.get("friends", []), start=1):
        try:
            friends.append(normalize_friend(raw_friend))
        except ValueError as e:
            warnings.append(f"好友#{index}: {e}")

    normalized = {
        "api_host": _strip_host(raw_config.get("api_host", "")),
        "api_key": (raw_config.get("api_key", "") or "").strip(),
        "message_template": (raw_config.get("message_template", "")
                             or DEFAULT_MESSAGE_TEMPLATE).strip(),
        "use_local_ocr": raw_config.get("use_local_ocr", True),
        "ocr_api_key": (raw_config.get("ocr_api_key", "") or "").strip(),
        "ocr_secret_key": (raw_config.get("ocr_secret_key", "") or "").strip(),
        "friends": friends,
    }
    return normalized, warnings


def validate_runtime_config(config: Dict) -> List[str]:
    errors: List[str] = []
    if not config.get("api_host"):
        errors.append("缺少 api_host")
    if not config.get("api_key"):
        errors.append("缺少 api_key（可在 config.json 或环境变量 DOUYIN_WEATHER_API_KEY 提供）")
    if not config.get("friends"):
        errors.append("好友列表为空")

    has_any_recognition = any(
        f.get("avatar_image") or f.get("avatar_text")
        for f in config.get("friends", [])
    )
    if config.get("friends") and not has_any_recognition:
        errors.append("所有好友都未配置识别方式（头像截图或OCR文字）")
    return errors


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

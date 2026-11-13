import json
import os
from typing import Dict, List, Tuple

DEFAULT_MESSAGE_TEMPLATE = (
    "Hi {nickname}，你所在的{city_name}今天白天{text_day}，晚上{text_night}。\n"
    "气温是{temp_min}到{temp_max}℃，{wind_dir}{wind_scale}级。"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def project_path(*parts: str) -> str:
    normalized_parts = [str(part) for part in parts]
    return os.path.join(BASE_DIR, *normalized_parts)


def _strip_host(host: str) -> str:
    host = (host or "").strip()
    if host.startswith("http://"):
        host = host[len("http://"):]
    if host.startswith("https://"):
        host = host[len("https://"):]
    return host.rstrip("/")


def load_config(config_path: str = CONFIG_PATH) -> Dict:
    if not os.path.exists(config_path):
        return {}

    with open(config_path, "r", encoding="utf-8") as config_file:
        try:
            return json.load(config_file)
        except json.JSONDecodeError as exc:
            raise ValueError(f"配置文件不是合法 JSON: {exc}") from exc


def save_config(config_data: Dict, config_path: str = CONFIG_PATH) -> None:
    with open(config_path, "w", encoding="utf-8") as config_file:
        json.dump(config_data, config_file, indent=2, ensure_ascii=False)


def normalize_config(raw_config: Dict) -> Tuple[Dict, List[str]]:
    warnings: List[str] = []
    friends: List[Dict] = []

    for index, raw_friend in enumerate(raw_config.get("friends", []), start=1):
        try:
            normalized = normalize_friend(raw_friend)
            friends.append(normalized)
        except ValueError as e:
            warnings.append(f"好友#{index}: {e}")

    normalized_config = {
        "api_host": _strip_host(raw_config.get("api_host", "")),
        "api_key": (raw_config.get("api_key", "") or "").strip(),
        "message_template": (raw_config.get("message_template", "") or DEFAULT_MESSAGE_TEMPLATE).strip(),
        "use_local_ocr": raw_config.get("use_local_ocr", True),
        "ocr_api_key": (raw_config.get("ocr_api_key", "") or "").strip(),
        "ocr_secret_key": (raw_config.get("ocr_secret_key", "") or "").strip(),
        "friends": friends,
    }
    return normalized_config, warnings


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

    if not city_name:
        city_name = f"ID:{location_id}"

    return {
        "nickname": nickname,
        "city_name": city_name,
        "location_id": location_id,
        # 保留旧版 city 字段，确保从 v6.0 切回 master 仍可读取
        "city": location_id,
        "avatar_image": avatar_image,
        "avatar_text": avatar_text,
    }


def validate_runtime_config(config: Dict) -> List[str]:
    errors: List[str] = []
    if not config.get("api_host"):
        errors.append("缺少 api_host")
    if not config.get("api_key"):
        errors.append("缺少 api_key（可在 config.json 或环境变量 DOUYIN_WEATHER_API_KEY 提供）")
    if not config.get("friends"):
        errors.append("好友列表为空")

    has_any_recognition = False
    for friend in config.get("friends", []):
        if friend.get("avatar_image") or friend.get("avatar_text"):
            has_any_recognition = True
            break

    if config.get("friends") and not has_any_recognition:
        errors.append("所有好友都未配置识别方式（头像截图或OCR文字）")

    return errors


# 常用城市 location_id（和风天气）速查
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


def search_city_by_name(name: str) -> list:
    """在城市速查表中搜索（用户输入后可下拉选择）"""
    if not name:
        return COMMON_CITIES[:10]
    name = name.strip().lower()
    results = [(c, cid) for c, cid in COMMON_CITIES if name in c]
    return results[:20]


def create_default_friend_template(nickname: str = "示例好友", city_name: str = "北京") -> Dict:
    """生成一个开箱即用的好友模板"""
    location_id = next((cid for c, cid in COMMON_CITIES if c == city_name), "101010100")
    return {
        "nickname": nickname,
        "city_name": city_name,
        "location_id": location_id,
        # 保留旧版 city 字段，确保从 v6.0 切回 master 仍可读取
        "city": location_id,
        "avatar_image": "",
        "avatar_text": "",
    }

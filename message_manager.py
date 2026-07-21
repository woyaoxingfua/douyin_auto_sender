import json
import os
import logging

from config_utils import project_path, load_config

logger = logging.getLogger(__name__)

MESSAGES_FILE = project_path('messages.json')

DEFAULT_PRESETS = [
    {
        "id": "weather",
        "name": "天气预报",
        "use_weather_api": True,
        "template": "Hi {nickname}，你所在的{city_name}今天白天{text_day}，晚上{text_night}。\n气温是{temp_min}到{temp_max}℃，{wind_dir}{wind_scale}级。",
        "variables": ["nickname", "city_name", "text_day", "text_night", "temp_min", "temp_max", "wind_dir", "wind_scale"],
    },
    {
        "id": "good_morning",
        "name": "早安问候",
        "use_weather_api": False,
        "template": "早上好 {nickname}！祝你今天工作顺利，心情愉快！",
        "variables": ["nickname"],
    },
    {
        "id": "good_night",
        "name": "晚安问候",
        "use_weather_api": False,
        "template": "晚安 {nickname}！好梦相伴，明天见！",
        "variables": ["nickname"],
    },
]


class MessageManager:
    def __init__(self):
        self.presets = []
        self.active_preset_id = "weather"
        self._load()

    def _load(self):
        try:
            if os.path.exists(MESSAGES_FILE):
                with open(MESSAGES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.presets = data.get('presets', [])
                self.active_preset_id = data.get('active_preset', 'weather')
            else:
                self.presets = DEFAULT_PRESETS.copy()
                self.active_preset_id = 'weather'
                self._save()
        except Exception as e:
            logger.error(f"加载消息预设失败: {e}")
            self.presets = DEFAULT_PRESETS.copy()
            self.active_preset_id = 'weather'

    def _save(self):
        try:
            data = {
                "presets": self.presets,
                "active_preset": self.active_preset_id,
            }
            with open(MESSAGES_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存消息预设失败: {e}")

    def get_active_preset(self):
        for p in self.presets:
            if p.get('id') == self.active_preset_id:
                return p
        return self.presets[0] if self.presets else None

    def set_active(self, preset_id):
        self.active_preset_id = preset_id
        self._save()

    def add_preset(self, name, template, use_weather_api=False):
        preset = {
            "id": f"preset_{int(time.time())}",
            "name": name,
            "use_weather_api": use_weather_api,
            "template": template,
            "variables": self._extract_variables(template),
        }
        self.presets.append(preset)
        self._save()
        return preset

    def update_preset(self, preset_id, name=None, template=None, use_weather_api=None):
        for p in self.presets:
            if p.get('id') == preset_id:
                if name is not None:
                    p['name'] = name
                if template is not None:
                    p['template'] = template
                    p['variables'] = self._extract_variables(template)
                if use_weather_api is not None:
                    p['use_weather_api'] = use_weather_api
                self._save()
                return p
        return None

    def delete_preset(self, preset_id):
        self.presets = [p for p in self.presets if p.get('id') != preset_id]
        if self.active_preset_id == preset_id:
            self.active_preset_id = self.presets[0]['id'] if self.presets else 'weather'
        self._save()

    def format_message(self, preset_id, data):
        preset = None
        for p in self.presets:
            if p.get('id') == preset_id:
                preset = p
                break

        if not preset:
            return None

        template = preset.get('template', '')
        try:
            return template.format(**data)
        except KeyError as e:
            logger.error(f"消息模板变量缺失: {e}")
            return template

    def _extract_variables(self, template):
        import re
        return list(set(re.findall(r'\{(\w+)\}', template)))

    def import_presets(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            imported = data.get('presets', [])
            self.presets.extend(imported)
            self._save()
            return len(imported)
        except Exception as e:
            logger.error(f"导入预设失败: {e}")
            return 0

    def export_presets(self, filepath):
        try:
            data = {"presets": self.presets, "active_preset": self.active_preset_id}
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"导出预设失败: {e}")
            return False


import time

import requests
import logging
from tenacity import retry, stop_after_attempt, wait_fixed
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True,
       retry=(RequestException))
def get_weather_data(city_name, nickname, api_key, api_host, location_id, message_template=None):
    """
    获取指定城市的天气数据并生成天气预报消息
    
    :param city_name: 城市名称
    :param nickname: 好友昵称
    :param api_key: 和风天气API密钥
    :param api_host: 和风天气API主机地址
    :param location_id: 城市ID
    :param message_template: 用户自定义消息模板，例如 "Hi {nickname}，你所在的{city_name}今天{text_day}..."
    :return: 格式化的天气预报消息字符串
    """
    logger.info(f"正在为 {city_name} (ID: {location_id}) 获取天气...")
    
    # 默认消息模板
    default_template = (
        "Hi {nickname}，你所在的{city_name}今天白天{text_day}，晚上{text_night}。\n"
        "气温是{temp_min}到{temp_max}℃，{wind_dir}{wind_scale}级。"
    )
    # 选择使用的模板
    final_template = message_template if message_template else default_template

    try:
        # 构造天气API请求URL
        weather_url = f"https://{api_host}/v7/weather/3d?location={location_id}&key={api_key}&lang=zh&unit=m"
        res_weather = requests.get(weather_url, timeout=5)
        res_weather.raise_for_status()
        data_weather = res_weather.json()

        # 检查API响应状态码
        if data_weather.get("code") == "200":
            # 提取今日天气信息
            today_weather = data_weather['daily'][0]
            text_day, text_night = today_weather['textDay'], today_weather['textNight']
            temp_max, temp_min = today_weather['tempMax'], today_weather['tempMin']
            wind_dir, wind_scale = today_weather['windDirDay'], today_weather['windScaleDay']

            # 将所有天气数据和昵称、城市名放入一个字典，用于模板格式化
            template_data = {
                "nickname": nickname,
                "city_name": city_name,
                "text_day": text_day,
                "text_night": text_night,
                "temp_max": temp_max,
                "temp_min": temp_min,
                "wind_dir": wind_dir,
                "wind_scale": wind_scale
            }
            # 构造基础天气预报消息
            weather_report = final_template.format(**template_data)

            # 根据天气条件添加特殊提醒
            if "雨" in text_day or "雨" in text_night:
                weather_report += " 出门记得带伞哦！"
            elif int(temp_min) < 5:
                weather_report += " 天气很冷，注意保暖呀！"
            elif int(temp_max) > 28:
                weather_report += " 天气炎热，小心中暑~"
            else:
                weather_report += " 祝你拥有愉快的一天！"
            return weather_report
        else:
            logger.error(f"获取天气失败。返回码: {data_weather.get('code')}。原始数据: {data_weather}")
            return None
    except RequestException as e: # Catch RequestException specifically for tenacity retry
        logger.error(f"获取天气时发生网络错误或API请求失败: {e}")
        raise # Re-raise the exception for tenacity to catch
    except Exception as e:
        logger.error(f"获取天气时发生未知错误: {e}")
        return None


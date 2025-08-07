import pyautogui
import requests
import time
import json
import os
import pyperclip

# 设置pyautogui的暂停时间和紧急停止功能
pyautogui.PAUSE = 0.5
pyautogui.FAILSAFE = True


def get_weather_data(city_name, nickname, api_key, api_host, location_id):
    """
    获取指定城市的天气数据并生成天气预报消息
    
    :param city_name: 城市名称
    :param nickname: 好友昵称
    :param api_key: 和风天气API密钥
    :param api_host: 和风天气API主机地址
    :param location_id: 城市ID
    :return: 格式化的天气预报消息字符串
    """
    print(f"  > 正在为 {city_name} (ID: {location_id}) 获取天气...")
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

            # 构造基础天气预报消息
            weather_report = f"Hi {nickname}，你所在的{city_name}今天白天{text_day}，晚上{text_night}。"
            weather_report += f"气温是{temp_min}到{temp_max}℃，{wind_dir}{wind_scale}级。"

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
            print(f"  [错误] 获取天气失败。返回码: {data_weather.get('code')}")
            return None
    except Exception as e:
        print(f"  [错误] 获取天气时发生网络错误: {e}")
        return None


def find_and_click(image_path, confidence=0.8, timeout=5):
    """
    在屏幕上查找图像并点击
    
    :param image_path: 要查找的图像路径
    :param confidence: 图像匹配的置信度阈值
    :param timeout: 查找超时时间（秒）
    :return: 成功找到并点击返回True，否则返回False
    """
    start_time = time.time()
    print(f"  > 正在寻找 '{image_path}'...")
    while time.time() - start_time < timeout:
        try:
            location = pyautogui.locateCenterOnScreen(image_path, confidence=confidence)
            if location:
                print(f"  > 找到 '{image_path}' 在 {location}，准备点击。")
                pyautogui.click(location)
                return True
        except pyautogui.PyAutoGUIException:
            pass
        time.sleep(1)
    print(f"  [失败] 超时！在 {timeout} 秒内未在屏幕上找到图片: '{image_path}'")
    return False


def scroll_by_dragging(scroll_bar_path, distance=200, duration=0.5):
    """
    通过拖动滚动条来滚动窗口。

    :param scroll_bar_path: 滚动条图像的路径
    :param distance: 拖动的距离（正数向下，负数向上），默认值改为 200
    :param duration: 拖动的持续时间（秒）
    """
    # 定位滚动条
    scroll_bar_location = pyautogui.locateCenterOnScreen(scroll_bar_path, confidence=0.8)
    if not scroll_bar_location:
        print(f"  [失败] 未能找到滚动条: '{scroll_bar_path}'")
        return False

    # 移动鼠标到滚动条上
    pyautogui.moveTo(scroll_bar_location)

    # 点击滚动条以选中它
    pyautogui.click()

    # 按下鼠标左键
    pyautogui.mouseDown()

    # 拖动鼠标
    pyautogui.moveRel(0, distance, duration=duration)

    # 释放鼠标左键
    pyautogui.mouseUp()

    print(f"  > 滚动条已拖动 {distance} 像素。")
    return True


def find_friend_with_scrolling(friend_avatar_path, scroll_bar_path, max_scrolls=10):
    """
    通过滚动查找好友头像并点击
    
    :param friend_avatar_path: 好友头像图像路径
    :param scroll_bar_path: 滚动条图像路径
    :param max_scrolls: 最大滚动次数
    :return: 成功找到并点击好友头像返回True，否则返回False
    """
    print(f"  > 开始滚动查找好友: {friend_avatar_path}")
    for i in range(max_scrolls):
        if find_and_click(friend_avatar_path, confidence=0.75, timeout=1):
            return True

        print(f"  > 页面{i + 1}未找到，尝试拖动滚动条...")

        # 尝试拖动滚动条，这里可以指定 distance 参数值
        if not scroll_by_dragging(scroll_bar_path, distance=200, duration=0.5):
            print("  [警告] 拖动滚动条失败，使用默认滚动。")
            pyautogui.scroll(-200)  # 如果拖动失败，使用默认滚动

        time.sleep(1)

    print(f"  [致命失败] 在滚动 {max_scrolls} 次后仍未找到好友: {friend_avatar_path}")
    return False


def main():
    """
    主函数：控制整个自动化流程
    """
    config_file = 'config.json'
    if not os.path.exists(config_file):
        print("[程序终止] 错误：找不到 config.json 配置文件！请先运行 config_manager_gui.py 来生成它。")
        return

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        api_host = config.get('api_host')
        api_key = config.get('api_key')
        friends_list = config.get('friends', [])
    except Exception as e:
        print(f"[程序终止] 读取配置文件失败: {e}")
        return

    if not api_key or not friends_list or not api_host:
        print("[程序终止] 错误：配置文件中的API Host、API Key或好友列表为空！请运行GUI程序进行配置。")
        return

    print("=" * 50)
    print("     抖音天气助手 v4.3 (最终流程版) - 自动化程序     ")
    print("=" * 50)
    print("请在10秒内将鼠标移动到抖音PC客户端内，并确保其为活动窗口...")
    for i in range(10, 0, -1):
        print(f"倒计时 {i} 秒...")
        time.sleep(1)

    scroll_bar_path = 'control_images/douyin_scroll_bar.png'  # 确保该路径正确指向滚动条图像

    # 遍历处理每个好友
    for friend in friends_list:
        # 兼容不同版本的配置文件格式
        nickname = friend['nickname']

        # 检查是否为新格式(V4.1及以上)
        if 'city_name' in friend and 'location_id' in friend:
            city_name = friend['city_name']
            location_id = friend['location_id']
            avatar_path = friend.get('avatar_image', '')
        # 检查是否为旧格式(V4.0及以前)
        elif 'city' in friend:
            # 旧格式使用城市ID作为city字段
            city_name = f"城市(ID: {friend['city']})"
            location_id = friend['city']
            avatar_path = friend.get('avatar_image', '')
        else:
            print(f"  [跳过] 好友 {nickname} 的配置格式不正确。")
            continue

        print(f"\n---=> 开始处理好友: 【{nickname}】 <=---")

        if avatar_path and not os.path.exists(avatar_path):
            print(f"  [跳过] 找不到头像文件: {avatar_path}。")
            continue

        # 每次循环都点击私信图标，确保好友列表是打开状态
        print("  > 正在点击\"私信\"图标以确保列表可见...")
        if not find_and_click('control_images/douyin_sixin_icon.png', timeout=3):
            print("  [严重错误] 找不到抖音的\"私信\"图标，任务无法继续。")
            break
        time.sleep(2)

        # 只有当有头像路径时才尝试查找好友
        if avatar_path:
            if not find_friend_with_scrolling(avatar_path, scroll_bar_path):
                print(f"  [跳过] 未能找到好友 {nickname}，将处理下一位。")
                continue
        time.sleep(3)

        weather_message = get_weather_data(city_name, nickname, api_key, api_host, location_id)
        if weather_message:
            print(f"  > 生成天气播报: {weather_message}")
            print("  > 正在输入消息 (使用剪贴板粘贴)...")

            pyperclip.copy(weather_message)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(1)

            print("  > 正在点击\"发送\"按钮...")
            if find_and_click('control_images/douyin_send_button.png'):
                print(f"  > 为 {nickname} 发送消息成功。")
                time.sleep(1)

                # --- (核心改动) --- 发送成功后，点击"退出会话"以返回列表
                print("  > 正在退出当前会话...")
                if not find_and_click('control_images/douyin_exit_chat_button.png'):
                    print("  [严重警告] 未能找到\"退出会话\"按钮！后续好友可能无法处理。")
                    break  # 如果无法退出，就终止整个任务，防止出错
            else:
                print(f"  [警告] 为 {nickname} 发送失败：未能点击发送按钮！")
        else:
            print(f"  [跳过] 因无法获取天气信息，未能向 {nickname} 发送。")

        print(f"  > 【{nickname}】处理完毕。")
        time.sleep(2)  # 退出会话后稍作等待，准备处理下一个

    print("\n" + "=" * 50)
    print(" 所有好友处理完毕，任务圆满结束！ ")
    print("=" * 50)


if __name__ == "__main__":
    main()
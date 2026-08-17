import json
import os
import random
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import ttk, messagebox
import mss
import cv2
import numpy as np
import pyautogui
from pynput import keyboard
import win32api
import win32con
from win32 import win32gui


def resource_path(relative_path):
    """返回源码目录或 PyInstaller 单文件解压目录中的资源路径。"""
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, relative_path)


def config_path():
    """开发时使用项目配置；打包后将用户配置保存在 EXE 同级目录。"""
    if not getattr(sys, 'frozen', False):
        return resource_path("config.json")
    return os.path.join(os.path.dirname(sys.executable), "config.json")


SKILL_LIST = [
    {'name': '矩阵', 'template': ['skill-jz.png']},
    {"name": "子弹", "template": ["skill.png"]},
    {"name": "温压弹", "template": ["skill-wyd.png", "skill-wyd-1.png"]},
    {"name": "干冰弹", "template": ["skill-gbd.png", "skill-gbd-1.png"]},
    {"name": "冰雹", "template": ["skill-bb.png", "skill-bb-1.png"]},
    {"name": "车", "template": ["skill-c.png", "skill-c-1.png"]},
    {"name": "电", "template": ["skill-d.png", "skill-d-1.png"]},
    {"name": "风刃", "template": ["skill-fr.png", "skill-fr-1.png"]},
    {"name": "激光", "template": ["skill-jg.png", "skill-jg-1.png"]},
    {"name": "龙卷风", "template": ["skill-ljf.png", "skill-ljf-1.png"]},
    {"name": "燃油", "template": ["skill-ry.png", "skill-ry-1.png"]},
    {"name": "射线", "template": ["skill-sx.png", "skill-sx-1.png"]},
    {"name": "无人机", "template": ["skill-wrj.png", "skill-wrj-1.png"]},
    {"name": "跃迁", "template": ["skill-yq.png", "skill-yq-1.png"]},
    {"name": "空投", "template": ["skill-kt.png", "skill-kt-1.png"]},
]

# 将第二形态合并进原有“子弹”选项，界面仍只显示一个子弹技能。
next(
    skill for skill in SKILL_LIST if skill['name'] == '子弹'
)['template'].extend(['skill-1.png', 'skill-1-original.png'])


class GameBot:
    def __init__(self, game_title="游戏窗口标题", battle_time=0, battle_count=0, mode=0, priority_skills=None):
        self.running = True
        self.group_wait_timeout = 30
        self.group_wait_started_at = None
        self.exit_deep_abyss = False
        self.exit_normal_stage = False
        self.exit_normal_stage_on_huanqiu = True
        self.prioritize_biochemical_bullet = True
        self.expecting_huanqiu_battle = False
        self.initial_skill_check_deadline = None
        self.battle_identify_not_before = None
        self.hotkey_listener = None
        self.sct = mss.mss()
        """初始化游戏机器人"""
        self.game_title = game_title
        self.battle_time = battle_time
        self.battle_count = battle_count
        self.game_window = None
        self.screenshot_dir = "screenshots"
        self.priority_skills = priority_skills if priority_skills else []

        # 单文件打包时，PyInstaller 会将内置模板解压到临时资源目录。
        self.template_dir = resource_path("templates")

        self.mode = mode

        # 创建必要的目录
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def find_game_window(self):
        """查找并激活游戏窗口"""
        hwnd = win32gui.FindWindow(None, self.game_title)
        if hwnd:
            win32gui.SetForegroundWindow(hwnd)
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            self.game_window = (left, top, right - left, bottom - top)
            print(f"找到游戏窗口: {self.game_window}")
            return True
        else:
            print("未找到游戏窗口")
            return False

    def find_fullscreen_window(self):
        """查找全屏幕窗口"""
        # 使用pyautogui获取屏幕尺寸，更简单可靠
        try:
            # 获取主屏幕尺寸
            width, height = pyautogui.size()
            left, top = 0, 0
            self.game_window = (left, top, width, height)
            print(f"全屏幕窗口: {self.game_window}")
            return True
        except Exception as e:
            print(f"获取屏幕尺寸时出错: {e}")
            # 如果pyautogui失败，尝试使用win32gui的基本方法
            try:
                width = win32gui.GetSystemMetrics(0)  # SM_CXSCREEN
                height = win32gui.GetSystemMetrics(1)  # SM_CYSCREEN
                left, top = 0, 0
                self.game_window = (left, top, width, height)
                print(f"使用备用方法获取全屏幕窗口: {self.game_window}")
                return True
            except Exception as e2:
                print(f"备用方法也失败: {e2}")
                return False

    def take_screenshot(self):
        if not hasattr(self, "_sct"):
            self._sct = mss.mss()  # ✅ 只创建一次

        if not self.game_window:
            if not self.find_game_window():
                return None

        left, top, width, height = self.game_window

        monitor = {
            "left": left,
            "top": top,
            "width": width,
            "height": height
        }

        screenshot = self._sct.grab(monitor)

        img = np.array(screenshot)
        return img[:, :, :3]  # BGRA → BGR

    def find_template(
            self,
            template_names,  # ✅ 支持字符串 或 数组
            threshold=0.8,
            use_gray=True,
            roi=None
    ):
        if not self.running:
            return None
        # ===== 0. 统一成数组 =====
        if isinstance(template_names, str):
            template_names = [template_names]

        # ===== 1. 初始化缓存 =====
        if not hasattr(self, "_template_cache"):
            self._template_cache = {}

        # ===== 2. 截图 =====
        img = self.take_screenshot()
        if img is None:
            return None

        # ===== 3. 灰度 =====
        if use_gray:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # ===== 4. ROI =====
        if roi:
            x, y, w, h = roi
            img = img[y:y + h, x:x + w]
            offset_x, offset_y = x, y
        else:
            offset_x, offset_y = 0, 0

        # ===== 5. 按顺序匹配（命中即返回） =====
        for template_name in template_names:
            template_name = str(template_name)
            cache_key = (template_name, use_gray)

            # ---- 读取 / 缓存模板 ----
            if cache_key not in self._template_cache:
                template_path = os.path.join(self.template_dir, template_name)

                if use_gray:
                    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
                else:
                    template = cv2.imread(template_path, cv2.IMREAD_COLOR)

                if template is None:
                    print(f"无法加载模板: {template_path}")
                    continue

                self._template_cache[cache_key] = template
            else:
                template = self._template_cache[cache_key]

            # ---- 模板匹配 ----
            result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            # ---- 命中直接返回 ----
            if max_val >= threshold:
                h, w = template.shape[:2]

                center_x = self.game_window[0] + offset_x + max_loc[0] + w // 2
                center_y = self.game_window[1] + offset_y + max_loc[1] + h // 2
                return center_x, center_y

        # ===== 全部没命中 =====
        return None

    def find_template1(self, template_name, threshold=0.8):
        # ===== 1. 模板缓存 =====
        global template_path
        if not hasattr(self, "_template_cache"):
            self._template_cache = {}

        if template_name not in self._template_cache:
            """在游戏窗口中查找模板图像"""
            template_path = os.path.join(self.template_dir, template_name)

            template_color = cv2.imread(template_path)
            if template_color is None:
                return []

            self._template_cache[template_name] = template_color
        else:
            template_color = self._template_cache[template_name]

        if template_color is None:
            print(f"无法加载模板: {template_path}")
            return None

        """在游戏窗口中查找模板图像"""
        img = self.take_screenshot()
        if img is None:
            return None

        # 模板匹配
        result = cv2.matchTemplate(img, template_color, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            h, w = template_color.shape[:2]
            center_x = self.game_window[0] + max_loc[0] + w // 2
            center_y = self.game_window[1] + max_loc[1] + h // 2
            return center_x, center_y

        # print(f"未找到匹配: {template_path}")
        return None

    def find_all_templates1(
            self,
            template_name,
            threshold=0.8,
            use_gray=True,  # ✅ 新增：灰度控制
            roi=None
    ):
        if not self.running:
            return []
        # ===== 1. 模板缓存 =====
        if not hasattr(self, "_template_cache"):
            self._template_cache = {}

        cache_key = (template_name, use_gray)

        if cache_key not in self._template_cache:
            template_path = os.path.join(self.template_dir, template_name)

            if use_gray:
                template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
            else:
                template = cv2.imread(template_path, cv2.IMREAD_COLOR)

            if template is None:
                print(f"无法加载模板: {template_path}")
                return []

            self._template_cache[cache_key] = template
        else:
            template = self._template_cache[cache_key]

        # ===== 2. 截图 =====
        img = self.take_screenshot()
        if img is None:
            return []

        # ===== 3. 灰度处理 =====
        if use_gray:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # ===== 4. ROI =====
        if roi:
            x, y, w, h = roi
            img = img[y:y + h, x:x + w]
            offset_x, offset_y = x, y
        else:
            offset_x, offset_y = 0, 0

        # ===== 5. 模板匹配 =====
        result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)

        # ===== 6. 阈值筛选 =====
        locations = np.where(result >= threshold)

        h, w = template.shape[:2]

        boxes = []
        scores = []

        # ⚠️ zip顺序是 (y, x)
        for y, x in zip(*locations):
            boxes.append([int(x), int(y), int(w), int(h)])
            scores.append(float(result[y, x]))

        if not boxes:
            return []

        # ===== 7. NMS 去重 =====
        indices = cv2.dnn.NMSBoxes(boxes, scores, threshold, 0.3)

        matches = []

        # ⚠️ OpenCV返回可能是 [[0],[1]] 或 [0,1]
        if len(indices) > 0:
            indices = np.array(indices).flatten()

            for i in indices:
                x, y, w, h = boxes[i]

                center_x = self.game_window[0] + offset_x + x + w // 2
                center_y = self.game_window[1] + offset_y + y + h // 2

                matches.append((center_x, center_y))

        return matches

    def find_all_templates(
            self,
            template_name,
            threshold=0.8,
            min_color_saturation=None,
            screenshot=None,
            roi=None,
    ):
        if not self.running:
            return []
        # ===== 1. 模板缓存 =====
        if not hasattr(self, "_template_cache"):
            self._template_cache = {}

        cache_key = ('color', template_name)
        if cache_key not in self._template_cache:
            template_path = os.path.join(self.template_dir, template_name)

            template_color = cv2.imread(template_path)
            if template_color is None:
                return []

            self._template_cache[cache_key] = template_color
        else:
            template_color = self._template_cache[cache_key]

        # ===== 2. 截图 =====
        img_color = screenshot if screenshot is not None else self.take_screenshot()
        if img_color is None:
            return []
        if roi:
            roi_x, roi_y, roi_w, roi_h = roi
            img_color = img_color[
                roi_y:roi_y + roi_h,
                roi_x:roi_x + roi_w,
            ]
        else:
            roi_x, roi_y = 0, 0
        # ===== 3. 彩色模板匹配 =====
        result = cv2.matchTemplate(img_color, template_color, cv2.TM_CCOEFF_NORMED)

        # ===== 4. 阈值筛选 =====
        locations = np.where(result >= threshold)

        h, w = template_color.shape[:2]

        # 只检查模板本身有明显颜色的像素。过期招募项会整体变灰，虽然轮廓
        # 仍能通过相关系数匹配，但这些位置的饱和度会显著降低。
        color_mask = None
        if min_color_saturation is not None:
            mask_key = ('color-mask', template_name)
            if mask_key not in self._template_cache:
                template_hsv = cv2.cvtColor(template_color, cv2.COLOR_BGR2HSV)
                self._template_cache[mask_key] = template_hsv[:, :, 1] >= 80
            color_mask = self._template_cache[mask_key]

        boxes = []
        scores = []

        for (y, x) in zip(*locations):
            if color_mask is not None:
                matched_patch = img_color[y:y + h, x:x + w]
                if matched_patch.shape[:2] != (h, w):
                    continue
                patch_saturation = cv2.cvtColor(
                    matched_patch, cv2.COLOR_BGR2HSV
                )[:, :, 1]
                if (
                    not np.any(color_mask)
                    or float(np.median(patch_saturation[color_mask]))
                    < min_color_saturation
                ):
                    continue
            boxes.append([x, y, w, h])
            scores.append(result[y, x])

        # ===== 5. NMS 去重 =====
        indices = cv2.dnn.NMSBoxes(boxes, scores, threshold, 0.3)

        matches = []

        for i in indices:
            x, y, w, h = boxes[i]

            center_x = self.game_window[0] + roi_x + x + w // 2
            center_y = self.game_window[1] + roi_y + y + h // 2

            matches.append((center_x, center_y))
        return matches

    def sleep_interruptible(self, seconds, step=0.1):
        """Sleep in small chunks so stop requests take effect quickly."""
        end_time = time.time() + seconds
        while self.running and time.time() < end_time:
            time.sleep(min(step, end_time - time.time()))
        return self.running
    def click(self, x, y, duration=0.2, human_like=True):
        """Click only while the bot is still running."""
        if not self.running:
            return False
        if human_like:
            x += random.randint(-5, 5)
            y += random.randint(-5, 5)
            duration += random.uniform(-0.1, 0.1)
            duration = max(0.1, duration)

        # SetCursorPos jumps immediately; moveTo(duration=...) creates a visible trail.
        win32api.SetCursorPos((int(x), int(y)))
        if not self.running:
            return False
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.02)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        print(f"点击位置: ({x}, {y})")
        return True

    def click_fast(self, x, y):
        """Fast click only while the bot is still running."""
        if not self.running:
            return False
        win32api.SetCursorPos((int(x), int(y)))
        time.sleep(0.015)
        if not self.running:
            return False
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.02)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        print(f"快速点击位置: ({x}, {y})")
        return True

    def press_key(self, key, presses=1, interval=0.1, human_like=True):
        """Press a key only while the bot is still running."""
        if not self.running:
            return False
        if human_like:
            interval += random.uniform(-0.05, 0.05)
            interval = max(0.05, interval)

        pyautogui.press(key, presses=presses, interval=interval)
        print(f"按下按键: {key}")
        return True
    def find_im(self):
        """判断能否发现环球页面"""
        im = self.find_template("im.png")
        if im:
            self.click(*im)
            self.sleep_interruptible(1)
            return True
        return False

    def find_click_continue(self):
        """判断能否发现继续按钮"""
        continue_button = self.find_template("click-continue.png")
        if continue_button:
            self.click(*continue_button)
            self.sleep_interruptible(0.2)

    def find_team_up(self):
        """判断能否发现队伍页面"""
        return self.find_template("team-up.png")

    def find_recruitment(self):
        while True and self.running:
            """判断能否发现招募页面"""
            team_up = self.find_team_up()
            if team_up:
                return True
            if not team_up:
                xy = self.find_template("recruitment.png")
                if not xy:
                    xy = self.find_template("recruitment-1.png")
                if xy:
                    self.click(*xy)
                    self.sleep_interruptible(0.2)
                else:
                    break
            self.find_reconnection()
            for i in range(30):
                if not self.running:
                    break
                try:
                    recruitment_frame = self.take_screenshot()
                    if recruitment_frame is None:
                        break
                    frame_height, frame_width = recruitment_frame.shape[:2]
                    recruitment_roi = (
                        int(frame_width * 0.32),
                        int(frame_height * 0.25),
                        int(frame_width * 0.40),
                        int(frame_height * 0.53),
                    )
                    huanqiu_positions = []
                    for template_name, threshold in [
                        ("huanqiu2.png", 0.7),
                        ("huanqiu.png", 0.75),
                        ("huanqiu1.png", 0.75),
                    ]:
                        huanqiu_positions.extend(self.find_all_templates(
                            template_name,
                            threshold=threshold,
                            min_color_saturation=45,
                            screenshot=recruitment_frame,
                            roi=recruitment_roi,
                        ))

                    deduped_positions = []
                    for pos in sorted(huanqiu_positions, key=lambda p: p[1], reverse=True):
                        if all(abs(pos[1] - old_pos[1]) > 25 for old_pos in deduped_positions):
                            deduped_positions.append(pos)

                    if deduped_positions:
                        # 一次只抢一个，点击后立即检查是否进队，避免页面变化后继续误点。
                        join_x = self.game_window[0] + int(self.game_window[2] * 0.82)
                        _, y = deduped_positions[0]
                        self.click_fast(join_x, y)
                        self.sleep_interruptible(0.05)
                        if self.find_team_up():
                            return True
                    else:
                        self.sleep_interruptible(0.03)  # 减少等待时间
                except Exception as e:
                    print("查找环球按钮时出错:", e)
                    traceback.print_exc()
                    self.sleep_interruptible(0.03)  # 减少等待时间

    def find_in_huanqiu_team(self):
        """是否在环球队伍"""
        title_roi = None
        if self.game_window:
            _, _, window_width, window_height = self.game_window
            title_roi = (
                0,
                int(window_height * 0.08),
                window_width,
                int(window_height * 0.12),
            )
        for attempt in range(3):
            if self.find_template(
                ['huanqiu-team-title.png', 'in-huanqiu-team.png'],
                threshold=0.72,
                use_gray=False,
                roi=title_roi,
            ):
                return True
            if attempt < 2:
                self.sleep_interruptible(0.05)
        return False

    def find_huanqiu_solo_invite(self):
        '''识别寰球队伍右下方的“+邀请”空位，即当前只有自己。'''
        if not self.game_window:
            return False
        _, _, window_width, window_height = self.game_window
        invite_roi = (
            int(window_width * 0.45),
            int(window_height * 0.70),
            int(window_width * 0.55),
            int(window_height * 0.20),
        )
        return self.find_template(
            'huanqiu-solo-invite.png',
            threshold=0.72,
            use_gray=False,
            roi=invite_roi,
        )

    def confirm_solo_huanqiu_team(self, confirmations=3, interval=0.3):
        """连续确认寰球队伍中仍显示“+邀请”空位，即当前只有自己。"""
        for attempt in range(confirmations):
            if not self.running:
                return False
            if not self.find_in_huanqiu_team() or not self.find_huanqiu_solo_invite():
                return False
            if attempt < confirmations - 1:
                self.sleep_interruptible(interval)
        return True

    def find_normal_stage_team(self):
        if not self.game_window:
            return False
        if not hasattr(self, '_template_cache'):
            self._template_cache = {}
        _, _, window_width, window_height = self.game_window
        tabs_roi = (
            0,
            int(window_height * 0.16),
            window_width,
            int(window_height * 0.22),
        )
        frame = self.take_screenshot()
        if frame is None:
            return False
        roi_x, roi_y, roi_width, roi_height = tabs_roi
        tabs_frame = frame[
            roi_y:roi_y + roi_height,
            roi_x:roi_x + roi_width,
        ]
        tabs_edges = cv2.Canny(
            cv2.cvtColor(tabs_frame, cv2.COLOR_BGR2GRAY),
            80,
            160,
        )
        centers = []
        for template_name in [
            'normal-stage-tab-normal.png',
            'normal-stage-tab-elite.png',
        ]:
            cache_key = ('edge', template_name)
            if cache_key not in self._template_cache:
                template = cv2.imread(
                    os.path.join(self.template_dir, template_name),
                    cv2.IMREAD_GRAYSCALE,
                )
                if template is None:
                    return False
                self._template_cache[cache_key] = cv2.Canny(
                    template,
                    80,
                    160,
                )
            edge_template = self._template_cache[cache_key]
            best_match = None
            # Support normal-stage tabs when the game window is scaled.
            for scale_percent in range(70, 141, 5):
                scale = scale_percent / 100
                scaled = edge_template if scale_percent == 100 else cv2.resize(
                    edge_template,
                    None,
                    fx=scale,
                    fy=scale,
                    interpolation=(
                        cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
                    ),
                )
                height, width = scaled.shape[:2]
                if height > tabs_edges.shape[0] or width > tabs_edges.shape[1]:
                    continue
                result = cv2.matchTemplate(
                    tabs_edges,
                    scaled,
                    cv2.TM_CCOEFF_NORMED,
                )
                _, score, _, location = cv2.minMaxLoc(result)
                if best_match is None or score > best_match[0]:
                    best_match = (float(score), location, width, height)
            if best_match is None or best_match[0] < 0.55:
                return False
            _, location, width, height = best_match
            centers.append((
                location[0] + width // 2,
                location[1] + height // 2,
            ))
        horizontal_gap = centers[1][0] - centers[0][0]
        return (
            int(window_width * 0.05) <= horizontal_gap <= int(window_width * 0.24)
            and abs(centers[1][1] - centers[0][1]) <= int(window_height * 0.025)
        )
        # else:
        #     leave = self.find_template("leave.png")
        #     if leave:
        #         print("在队伍中")
        #         self.click(*leave)
        #         queding = self.find_template("queding.png")
        #         if queding:
        #             self.click(*queding)

    def find_home_close(self):
        """判断能否发现关闭按钮"""
        close = self.find_template("home-close.png")
        if not close:
            close = self.find_template("home-close-1.png")

        if not close and self.find_template("home-close-2-text.png"):
            close = self.find_template("home-close-2.png")
        if not close and self.find_template("return-2.png"):
            close = self.find_template("return-2.png")

        if close:
            self.click(*close)
            self.sleep_interruptible(0.2)

    def find_close(self):
        closes = [
            "close.png",
            "auto-close.png",
            "battling-4.png",
        ]
        for close in closes:
            close = self.find_template(close)
            if close:
                self.click(*close)
                self.sleep_interruptible(0.2)
                return True
        return False

    def find_reconnection(self):
        """判断能否发现重新连接按钮"""
        reconnection = self.find_template("reconnection.png")
        if reconnection:
            self.click(*reconnection)
            self.sleep_interruptible(0.2)

    def find_huanqiu(self):
        """判断能否发现环球按钮"""
        return self.find_template("huanqiu.png")

    def find_start_button(self):
        """找到战斗位置"""
        battle = self.find_template("battle.png")
        if not battle:
            battle = self.find_template("battle-1.png", threshold=0.7)
        if battle:
            self.click(*battle)
            self.sleep_interruptible(0.2)
            return True
        return False

    def find_sure(self):
        """判断能否发现确定按钮"""
        sure = self.find_template("sure.png")
        if sure:
            self.click(*sure)
            self.sleep_interruptible(0.2)

    def find_battling_continue(self):
        """判断能否发现继续战斗按钮"""
        continue_battle = self.find_template("battling-continue.png")
        if continue_battle:
            self.click(*continue_battle)
            self.sleep_interruptible(0.2)

    def _find_skill_legacy(self):
        """判断能否发现技能按钮"""
        skill_roi = None
        if self.game_window:
            _, _, window_width, window_height = self.game_window
            skill_roi = (
                0,
                int(window_height * 0.39),
                window_width,
                int(window_height * 0.22)
            )

        # 首先检查4个优先技能
        for priority_skill_templates in self.priority_skills:
            if priority_skill_templates:
                # priority_skill_templates 是模板文件名列表
                for template in priority_skill_templates:
                    # 确保文件名包含.png扩展名
                    if not template.endswith('.png'):
                        template = f"{template}.png"
                    is_second_bullet = template.startswith('skill-1')
                    skill_pos = self.find_template(
                        template,
                        threshold=0.72 if is_second_bullet else 0.8,
                        use_gray=not is_second_bullet,
                        roi=skill_roi,
                    )
                    if skill_pos:
                        self.click(*skill_pos)
                        self.sleep_interruptible(0.2)
                        return None

        # 如果优先技能未匹配到，从全部技能中按顺序匹配
        for skill in SKILL_LIST:
            for template in skill["template"]:
                # 确保文件名包含.png扩展名
                if not template.endswith('.png'):
                    template = f"{template}.png"
                is_second_bullet = template.startswith('skill-1')
                skill_pos = self.find_template(
                    template,
                    threshold=0.72 if is_second_bullet else 0.8,
                    use_gray=not is_second_bullet,
                    roi=skill_roi,
                )
                if skill_pos:
                    self.click(*skill_pos)
                    self.sleep_interruptible(0.2)
                    return None

        return None

    def find_skill(self):
        '''在同一帧中按优先级选择置信度最高的技能。'''
        if not self.game_window:
            return None
        frame = self.take_screenshot()
        if frame is None:
            return None
        _, _, window_width, window_height = self.game_window
        if self.prioritize_biochemical_bullet:
            biochemical_roi = (
                0,
                int(window_height * 0.35),
                window_width,
                int(window_height * 0.12),
            )
            biochemical_bullet = self.find_template(
                'skill-biochemical-bullet-title.png',
                threshold=0.92,
                use_gray=False,
                roi=biochemical_roi,
            )
            if biochemical_bullet:
                print('检测到生化子弹，忽略技能优先级顺序并直接选择')
                self.click(*biochemical_bullet)
                self.sleep_interruptible(0.2)
                return True

        roi_y = int(window_height * 0.39)
        roi_height = int(window_height * 0.22)
        skill_frame = frame[roi_y:roi_y + roi_height, 0:window_width]

        def best_match(template_names):
            best = None
            for template_name in template_names:
                if not template_name.endswith('.png'):
                    template_name = f'{template_name}.png'
                match = self.match_skill_template(skill_frame, template_name)
                if match and (best is None or match[0] > best[0]):
                    best = match
            return best

        # 当前优先级的所有形态一起比较，避免先匹配到相似但错误的图标。
        for template_names in self.priority_skills:
            match = best_match(template_names)
            if match:
                _, x, y = match
                self.click(
                    self.game_window[0] + x,
                    self.game_window[1] + roi_y + y,
                )
                self.sleep_interruptible(0.2)
                return True

        # 没有优先技能时选择全局最高分，不再按模板列表顺序命中即点。
        match = best_match([
            template_name
            for skill in SKILL_LIST
            for template_name in skill['template']
        ])
        if match:
            _, x, y = match
            self.click(
                self.game_window[0] + x,
                self.game_window[1] + roi_y + y,
            )
            self.sleep_interruptible(0.2)
            return True
        return None

    def match_skill_template(self, skill_frame, template_name):
        '''彩色多尺度匹配技能，返回分数及相对中心坐标。'''
        if not hasattr(self, '_template_cache'):
            self._template_cache = {}
        cache_key = ('skill-color', template_name)
        if cache_key not in self._template_cache:
            template = cv2.imread(
                os.path.join(self.template_dir, template_name),
                cv2.IMREAD_COLOR,
            )
            if template is None:
                return None
            self._template_cache[cache_key] = template
        template = self._template_cache[cache_key]
        is_small_template = max(template.shape[:2]) <= 40
        is_second_bullet = template_name.startswith('skill-1')
        if is_small_template:
            threshold = 0.86
        elif is_second_bullet:
            threshold = 0.72
        else:
            threshold = 0.86
        best = None
        for scale in (0.92, 1.0, 1.08):
            scaled = template if scale == 1.0 else cv2.resize(
                template,
                None,
                fx=scale,
                fy=scale,
                interpolation=(
                    cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
                ),
            )
            height, width = scaled.shape[:2]
            if height > skill_frame.shape[0] or width > skill_frame.shape[1]:
                continue
            result = cv2.matchTemplate(
                skill_frame,
                scaled,
                cv2.TM_CCOEFF_NORMED,
            )
            _, score, _, location = cv2.minMaxLoc(result)
            if best is None or score > best[0]:
                best = (
                    float(score),
                    location[0] + width // 2,
                    location[1] + height // 2,
                )
        if best and best[0] >= threshold:
            return best
        return None

    def find_deep_abyss(self):
        '''判断当前战斗是否为顶部显示“第X层”的深渊同行。'''
        if not self.game_window:
            return False
        _, _, window_width, window_height = self.game_window
        top_roi = (0, 0, window_width, int(window_height * 0.16))
        prefix = self.find_template(
            'deep-abyss-floor-prefix.png',
            threshold=0.72,
            use_gray=False,
            roi=top_roi,
        )
        if not prefix:
            return False
        suffix = self.find_template(
            'deep-abyss-floor-suffix.png',
            threshold=0.72,
            use_gray=False,
            roi=top_roi,
        )
        if not suffix:
            return False
        horizontal_gap = suffix[0] - prefix[0]
        return 25 <= horizontal_gap <= 70 and abs(suffix[1] - prefix[1]) <= 12

    def find_huanqiu_battle_title(self, roi):
        '''对战斗页标题进行彩色多尺度匹配，兼容不同窗口缩放。'''
        frame = self.take_screenshot()
        if frame is None:
            return False
        roi_x, roi_y, roi_width, roi_height = roi
        title_frame = frame[
            roi_y:roi_y + roi_height,
            roi_x:roi_x + roi_width,
        ]
        if not hasattr(self, '_template_cache'):
            self._template_cache = {}
        best_score = 0.0
        for template_name in [
            'in-huanqiu-team.png',
            'huanqiu-team-title.png',
        ]:
            template_key = ('huanqiu-battle-original', template_name)
            if template_key not in self._template_cache:
                template = cv2.imread(
                    os.path.join(self.template_dir, template_name),
                    cv2.IMREAD_COLOR,
                )
                if template is None:
                    continue
                self._template_cache[template_key] = template
            template = self._template_cache[template_key]
            for scale_percent in range(45, 106, 3):
                scale_key = (
                    'huanqiu-battle-scaled',
                    template_name,
                    scale_percent,
                )
                if scale_key not in self._template_cache:
                    scale = scale_percent / 100
                    self._template_cache[scale_key] = cv2.resize(
                        template,
                        None,
                        fx=scale,
                        fy=scale,
                        interpolation=cv2.INTER_AREA,
                    )
                scaled = self._template_cache[scale_key]
                height, width = scaled.shape[:2]
                if height > title_frame.shape[0] or width > title_frame.shape[1]:
                    continue
                result = cv2.matchTemplate(
                    title_frame,
                    scaled,
                    cv2.TM_CCOEFF_NORMED,
                )
                _, score, _, _ = cv2.minMaxLoc(result)
                best_score = max(best_score, float(score))
                if score >= 0.68:
                    return True
        self.last_huanqiu_battle_score = best_score
        return False

    def find_huanqiu_battle(self):
        '''在战斗页顶部再次确认是否显示寰球救援标题。'''
        if not self.game_window:
            return False
        _, _, window_width, window_height = self.game_window
        top_roi = (0, 0, window_width, int(window_height * 0.24))
        for attempt in range(3):
            if self.find_huanqiu_battle_title(top_roi):
                return True
            if self.find_template(
                [
                    'huanqiu-team-title.png',
                    'in-huanqiu-team.png',
                    'huanqiu2.png',
                    'huanqiu.png',
                    'huanqiu1.png',
                ],
                threshold=0.68,
                use_gray=False,
                roi=top_roi,
            ):
                return True
            if attempt < 2:
                self.sleep_interruptible(0.1)
        return False

    def dismiss_activated_skill_page(self):
        '''识别“已激活技能”页，并点击弹窗上方空白处关闭。'''
        if not self.game_window:
            return False
        auto_close = self.find_template('auto-close.png', threshold=0.75)
        if not auto_close:
            return False
        left, top, width, height = self.game_window
        self.click(left + width // 2, top + int(height * 0.18))
        self.sleep_interruptible(0.3)
        return True

    def find_battling(self):
        """判断是否在战斗中"""
        xy = self.find_template("battling.png")
        if not xy:
            xy = self.find_template("battling-2.png")
        if not xy:
            xy = self.find_template("battling-3.png")
        if not xy:
            xy = self.find_template("battling-4.png")
        if not xy:
            xy = self.find_template("battling-5.png")
        return xy

    def find_dont_battle_return(self):
        """判断是否有返回按钮"""
        return_button = self.find_template("return-1.png", use_gray=False)
        if return_button:
            self.click(*return_button)
            self.sleep_interruptible(0.2)
            return True
        return False

    def find_return(self):
        """判断是否在返回主界面"""
        return_button = self.find_template("return.png")
        if not return_button:
            return_button = self.find_template("return-2.png")

        if return_button:
            self.click(*return_button)
            self.sleep_interruptible(0.2)

    def find_stop(self):
        """判断能否发现停止按钮"""
        stop = self.find_template("battling.png")
        if stop:
            self.click(*stop)
            self.sleep_interruptible(0.2)

    def find_exit(self):
        """判断能否发现退出按钮"""
        exit_button = self.find_template("exit.png")
        if exit_button:
            self.click(*exit_button)
            self.sleep_interruptible(0.2)
            return True
        return False

    def find_card(self):
        """判断能否发现卡关按钮"""
        card = self.find_template("card-normal.png")
        if card:
            self.click(*card)
            self.sleep_interruptible(0.2)
            card = self.find_template("card-start.png")
            if card:
                self.click(*card)
                self.sleep_interruptible(0.2)

    def find_orange_start_game(self):
        """判断能否发现橘子开始游戏按钮"""
        orange_start_game = self.find_template("orange-start.png")
        print(orange_start_game)
        if orange_start_game:
            self.click(*orange_start_game)
            self.sleep_interruptible(0.2)

    def on_hotkey(self, key):
        """快捷键回调函数"""
        try:
            if key == keyboard.Key.esc:
                print("检测到ESC键，正在停止脚本...")
                self.running = False
                if self.hotkey_listener:
                    self.hotkey_listener.stop()
                return False
        except AttributeError:
            pass
        return True

    def setup_hotkey(self):
        """设置快捷键监听"""
        print("已设置快捷键: ESC键 - 停止脚本")
        self.hotkey_listener = keyboard.Listener(on_release=self.on_hotkey)
        self.hotkey_listener.start()

    def main_loop(self, iterations=None):
        """主循环"""
        # 设置快捷键监听
        self.setup_hotkey()

        print("开始自动刷图脚本...")
        print("提示: 按下ESC键可以随时停止脚本")
        count = self.battle_count

        # timestamp = time.time()
        while self.running:
            # 检查是否达到迭代次数
            if iterations and count >= iterations:
                print(f"已完成 {iterations} 次刷图，脚本停止")
                self.running = False
                break

            # 确保游戏窗口被找到
            if not self.game_window and not self.find_game_window():
                self.sleep_interruptible(5)
                continue
            # 关闭按钮
            self.find_home_close()

            # 检查是否需要重新连接
            self.find_reconnection()

            # 是否确定
            self.find_sure()

            # 是不是通关了
            self.find_return()

            batileTime = None
            battle_seen = False
            # 是不是在战斗中
            while True and self.running:

                if self.mode == 2:
                    self.find_fullscreen_window()
                    # 检查开始游戏是否可点击
                    self.find_orange_start_game()
                    self.sleep_interruptible(10)
                    continue

                battling = self.find_battling()
                if not battling:
                    break
                self.group_wait_started_at = None
                battle_seen = True
                if self.initial_skill_check_deadline is None:
                    self.initial_skill_check_deadline = time.time() + 15
                    self.battle_identify_not_before = time.time() + 2
                    print('已进入战斗，将在前15秒检测可能出现的初始技能页')
                if time.time() < self.initial_skill_check_deadline:
                    if self.dismiss_activated_skill_page():
                        print('已关闭“已激活技能”页，等待战斗界面稳定')
                        self.battle_identify_not_before = time.time() + 2
                        self.sleep_interruptible(0.5)
                        continue
                    skill_selected = self.find_skill()
                    if skill_selected:
                        print('已处理普通技能选择页，等待页面消失后再判断关卡')
                        self.battle_identify_not_before = time.time() + 1.2
                        self.sleep_interruptible(0.5)
                        continue
                    if time.time() < self.battle_identify_not_before:
                        self.sleep_interruptible(0.2)
                        continue

                if (
                    self.mode == 0
                    and self.exit_normal_stage_on_huanqiu
                    and (self.exit_normal_stage or not self.expecting_huanqiu_battle)
                    and self.find_huanqiu_battle()
                ):
                    print('已在战斗页确认是寰球远征，取消普通关卡退出')
                    self.exit_normal_stage = False
                    self.expecting_huanqiu_battle = True

                if (
                    self.mode == 0
                    and self.exit_normal_stage_on_huanqiu
                    and (
                        self.exit_normal_stage
                        or not self.expecting_huanqiu_battle
                    )
                ):
                    print('打寰球过程中检测到误入普通关卡，正在退出战斗')
                    self.find_stop()
                    if self.find_exit():
                        self.exit_normal_stage = False
                        self.expecting_huanqiu_battle = False
                    break
                if self.exit_deep_abyss and self.find_deep_abyss():
                    print('检测到深渊同行，正在退出战斗')
                    self.find_stop()
                    self.find_exit()
                    break
                print("正在战斗中")
                # 点击技能
                self.find_skill()
                # 点击继续战斗
                self.find_battling_continue()
                self.sleep_interruptible(3)
                # 点击重新连接
                self.find_reconnection()
                # 关闭窗口
                self.find_close()
                # 点击返回
                self.find_return()

                if batileTime is None:
                    batileTime = time.time()
                else:
                    if self.battle_time > 0 and time.time() - batileTime > self.battle_time:
                        print(f"战斗时间超过{self.battle_time}秒,退出")
                        self.find_stop()
                        self.find_exit()
                print("战斗时间:", time.time() - batileTime)
            # 是否刷环球
            if self.mode == 0:
                battling = self.find_battling()
                if battling:
                    self.running = True
                    continue
                # 先找是不是在招募中
                self.find_recruitment()
                # 是否已经进入环球队伍
                in_huanqiu_team = self.find_in_huanqiu_team()
                team_up = self.find_team_up()
                normal_stage_team = (
                    self.find_normal_stage_team()
                    or (team_up and not in_huanqiu_team)
                )
                if team_up or normal_stage_team:
                    self.initial_skill_check_deadline = None
                    self.battle_identify_not_before = None

                if (
                    self.exit_normal_stage_on_huanqiu
                    and normal_stage_team
                    and not in_huanqiu_team
                ):
                    print('明确识别到普通关卡准备界面，正在判断是否已组队')
                    self.exit_normal_stage = True
                    self.expecting_huanqiu_battle = False
                    self.group_wait_started_at = None
                    exited_team = self.find_dont_battle_return()
                    if exited_team:
                        print('已发现退出队伍按钮，正在退出当前队伍')
                        self.find_click_continue()
                        self.exit_normal_stage = False
                        self.sleep_interruptible(0.5)
                    else:
                        normal_start_button = self.find_template('battle.png')
                        if not normal_start_button:
                            normal_start_button = self.find_template(
                                'battle-1.png',
                                threshold=0.7,
                            )
                        if normal_start_button:
                            print('当前未组队，正在返回寰球招募频道')
                            if self.find_im():
                                self.find_recruitment()
                                self.exit_normal_stage = False
                            else:
                                print('等待招募频道入口出现')
                                self.sleep_interruptible(0.5)
                    continue
                if in_huanqiu_team:
                    self.exit_normal_stage = False
                    self.expecting_huanqiu_battle = True
                    if self.confirm_solo_huanqiu_team():
                        print('连续确认寰球队伍中只有自己，立即退出后重新招募')
                        self.group_wait_started_at = None
                        self.expecting_huanqiu_battle = False
                        self.find_dont_battle_return()
                        self.find_click_continue()
                        continue

            # 先确定位置
            start_button = self.find_start_button()
            if not start_button:
                # 抢到寰球救援后，组队界面可能还在等待队长开始。此时
                # return-1.png 是“退出队伍”，不能当成普通返回按钮点击。
                if self.mode == 0 and (
                    in_huanqiu_team or team_up
                ):
                    if self.group_wait_started_at is None:
                        self.group_wait_started_at = time.time()
                    wait_seconds = time.time() - self.group_wait_started_at
                    if (
                        self.group_wait_timeout > 0
                        and wait_seconds >= self.group_wait_timeout
                    ):
                        print(f'组队等待超过{self.group_wait_timeout}秒，退出后重新招募')
                        self.group_wait_started_at = None
                        self.expecting_huanqiu_battle = False
                        self.find_dont_battle_return()
                        self.find_click_continue()
                        continue
                    print(
                        f'已进入寰球救援队伍，等待开始：'
                        f'{int(wait_seconds)}/{self.group_wait_timeout}秒'
                    )
                    self.sleep_interruptible(2)
                    continue
                self.group_wait_started_at = None
                # 不打远征
                self.find_dont_battle_return()
                self.find_click_continue()
                continue
            self.group_wait_started_at = None
            # 是否刷环球
            if self.mode == 0:
                # 检查当前页面是否在环球页面
                self.find_im()
            # 是否刷卡关
            if self.mode == 1:
                # 检查当前页面是否在卡关页面
                self.find_card()
            # 点击继续
            self.find_click_continue()
            # 每100秒随机点个位置
            # if time.time() - timestamp > 100:
            # 随机点击
            # self.click(random.randint(int(self.game_window[2]), int(self.game_window[0])), random.randint(int(self.game_window[1]), int(self.game_window[3])))
            # self.click(500, 100)
            # timestamp = time.time()


class GameBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("游戏机器人操作界面")
        self.root.geometry("600x790")
        self.root.resizable(False, False)

        self.bot = None
        self.is_running = False
        self.config_file = config_path()

        # 创建界面组件
        self.create_widgets()

        # 加载保存的配置
        self.load_config()

    def get_skill_template_by_name(self, name):
        """根据技能名称获取模板文件名列表"""
        for skill in SKILL_LIST:
            if skill["name"] == name:
                return skill["template"]
        return None

    def load_config(self):
        """加载保存的配置"""
        try:
            # 首次运行 EXE 时读取内置默认配置；保存后读取用户配置。
            load_path = self.config_file
            if not os.path.exists(load_path):
                load_path = resource_path("config.json")
            if os.path.exists(load_path):
                with open(load_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.group_wait_timeout_var.set(
                        config.get('group_wait_timeout', 30)
                    )
                    self.exit_deep_abyss_var.set(
                        config.get('exit_deep_abyss', False)
                    )
                    self.exit_normal_stage_var.set(
                        config.get('exit_normal_stage_on_huanqiu', True)
                    )
                    self.prioritize_biochemical_bullet_var.set(
                        config.get('prioritize_biochemical_bullet', True)
                    )
                    # 加载优先技能配置
                    priority_skills = config.get('priority_skills', [])
                    for i, skill_name in enumerate(priority_skills):
                        if i < len(self.priority_skill_vars):
                            self.priority_skill_vars[i].set(skill_name)
        except Exception as e:
            print(f"加载配置失败: {e}")

    def save_config(self):
        """保存当前配置"""
        try:
            config = {
                'priority_skills': [var.get() for var in self.priority_skill_vars],
                'group_wait_timeout': self.group_wait_timeout_var.get(),
                'exit_deep_abyss': self.exit_deep_abyss_var.get(),
                'exit_normal_stage_on_huanqiu': (
                    self.exit_normal_stage_var.get()
                ),
                'prioritize_biochemical_bullet': (
                    self.prioritize_biochemical_bullet_var.get()
                ),

            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def create_widgets(self):
        # 游戏标题
        ttk.Label(self.root, text="游戏窗口标题:").grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)
        self.game_title_var = tk.StringVar(value="向僵尸开炮")
        ttk.Entry(self.root, textvariable=self.game_title_var, width=30).grid(row=0, column=1, padx=10, pady=5)

        # 模式选择
        ttk.Label(self.root, text="模式:").grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)
        self.mode_var = tk.IntVar(value=0)
        mode_frame = ttk.Frame(self.root)
        mode_frame.grid(row=1, column=1, padx=10, pady=5, sticky=tk.W)
        ttk.Radiobutton(mode_frame, text="打环球", variable=self.mode_var, value=0).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="刷卡关", variable=self.mode_var, value=1).pack(side=tk.LEFT)
        # ttk.Radiobutton(mode_frame, text="全屏模式", variable=self.mode_var, value=2).pack(side=tk.LEFT)

        # 战斗次数
        ttk.Label(self.root, text="战斗次数:").grid(row=2, column=0, padx=10, pady=5, sticky=tk.W)
        self.battle_count_var = tk.IntVar(value=0)
        ttk.Spinbox(self.root, from_=0, to=999, textvariable=self.battle_count_var, width=10).grid(row=2, column=1,
                                                                                                   padx=10, pady=5,
                                                                                                   sticky=tk.W)
        ttk.Label(self.root, text="(0表示无限循环)").grid(row=2, column=2, padx=5, pady=5, sticky=tk.W)

        # 战斗时间
        ttk.Label(self.root, text="战斗时间(秒):").grid(row=3, column=0, padx=10, pady=5, sticky=tk.W)
        self.battle_time_var = tk.IntVar(value=0)
        ttk.Spinbox(self.root, from_=0, to=999, textvariable=self.battle_time_var, width=10).grid(row=3, column=1,
                                                                                                  padx=10, pady=5,
                                                                                                  sticky=tk.W)
        ttk.Label(self.root, text="(0表示无限制)").grid(row=3, column=2, padx=5, pady=5, sticky=tk.W)

        # 提示标签
        ttk.Label(self.root, text="提示: 按ESC键暂停脚本", foreground="blue").grid(row=4, column=0, columnspan=3,
                                                                                   padx=10, pady=5, sticky=tk.W)

        # 优先技能选项（5个）
        ttk.Label(self.root, text="优先技能(从上到下):").grid(row=5, column=0, padx=10, pady=5, sticky=tk.W)

        # 获取技能名称列表
        skill_names = [skill["name"] for skill in SKILL_LIST]

        # 5个优先技能下拉框
        self.priority_skill_vars = []
        self.priority_skill_combos = []
        for i in range(5):
            var = tk.StringVar(value="")
            self.priority_skill_vars.append(var)
            combo = ttk.Combobox(self.root, textvariable=var, values=[""] + skill_names, width=15, state="readonly")
            combo.grid(row=5 + i, column=1, padx=10, pady=3, sticky=tk.W)
            combo.bind("<<ComboboxSelected>>", self.on_skill_selected)
            self.priority_skill_combos.append(combo)
            ttk.Label(self.root, text=f"优先级{i + 1}").grid(row=5 + i, column=2, padx=5, pady=3, sticky=tk.W)

        # 按钮框架
        button_frame = ttk.Frame(self.root)
        button_frame.grid(row=10, column=0, columnspan=3, padx=10, pady=20)

        # 开始按钮
        self.start_btn = ttk.Button(button_frame, text="开始", command=self.start_bot, width=15)
        self.start_btn.pack(side=tk.LEFT, padx=10)

        # 停止按钮
        self.stop_btn = ttk.Button(button_frame, text="停止", command=self.stop_bot, width=15, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=10)

        # 退出按钮
        self.quit_btn = ttk.Button(button_frame, text="退出", command=self.quit_app, width=15)
        self.quit_btn.pack(side=tk.LEFT, padx=10)

        # 状态标签
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, foreground="green").grid(row=11, column=0, columnspan=3,
                                                                                    padx=10, pady=10)

        ttk.Label(self.root, text='组队等待时间(秒):').grid(
            row=12, column=0, padx=10, pady=5, sticky=tk.W
        )
        self.group_wait_timeout_var = tk.IntVar(value=30)
        ttk.Spinbox(
            self.root,
            from_=0,
            to=999,
            textvariable=self.group_wait_timeout_var,
            width=10,
        ).grid(row=12, column=1, padx=10, pady=5, sticky=tk.W)
        ttk.Label(self.root, text='(0表示一直等待)').grid(
            row=12, column=2, padx=5, pady=5, sticky=tk.W
        )

        self.exit_deep_abyss_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.root,
            text='深渊同行战斗时自动退出',
            variable=self.exit_deep_abyss_var,
        ).grid(row=13, column=0, columnspan=3, padx=10, pady=5, sticky=tk.W)

        self.exit_normal_stage_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self.root,
            text='打寰球时误入普通关卡自动退出',
            variable=self.exit_normal_stage_var,
        ).grid(row=14, column=0, columnspan=3, padx=10, pady=5, sticky=tk.W)
        self.prioritize_biochemical_bullet_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self.root,
            text='生化子弹出现时无视技能优先级',
            variable=self.prioritize_biochemical_bullet_var,
        ).grid(row=15, column=0, columnspan=3, padx=10, pady=5, sticky=tk.W)


    def on_skill_selected(self, event):
        """技能选择事件，防止重复选择"""
        # 获取所有已选择的技能
        selected_skills = [var.get() for var in self.priority_skill_vars if var.get()]

        # 获取所有技能名称
        all_skills = [skill["name"] for skill in SKILL_LIST]

        # 更新每个下拉框的可选项
        for i, combo in enumerate(self.priority_skill_combos):
            current_value = self.priority_skill_vars[i].get()
            # 可选项：空 + 未被其他下拉框选中的技能
            available = [""] + [s for s in all_skills if s not in selected_skills or s == current_value]
            combo['values'] = available

    def start_bot(self):
        """开始运行游戏机器人"""
        try:
            # 获取界面参数
            game_title = self.game_title_var.get()
            mode = self.mode_var.get()
            battle_count = self.battle_count_var.get()
            battle_time = self.battle_time_var.get()
            group_wait_timeout = max(0, self.group_wait_timeout_var.get())
            exit_deep_abyss = self.exit_deep_abyss_var.get()
            exit_normal_stage = self.exit_normal_stage_var.get()
            prioritize_biochemical_bullet = self.prioritize_biochemical_bullet_var.get()

            # 获取5个优先技能（将中文名称转换为模板文件名）
            priority_skills = []
            for var in self.priority_skill_vars:
                skill_name = var.get()
                if skill_name:
                    template = self.get_skill_template_by_name(skill_name)
                    if template:
                        priority_skills.append(template)

            # 保存配置
            self.save_config()

            # 验证参数
            if not game_title:
                messagebox.showerror("错误", "请输入游戏窗口标题")
                return

            # 创建GameBot实例
            self.bot = GameBot(game_title, battle_time, battle_count, mode, priority_skills)
            self.bot.group_wait_timeout = group_wait_timeout
            self.bot.exit_deep_abyss = exit_deep_abyss
            self.bot.exit_normal_stage_on_huanqiu = exit_normal_stage
            self.bot.prioritize_biochemical_bullet = prioritize_biochemical_bullet

            # 更新状态
            self.status_var.set("运行中...")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)

            # 创建并启动线程
            self.bot_thread = threading.Thread(target=self.run_bot, daemon=True)
            self.bot_thread.start()

        except Exception as e:
            messagebox.showerror("错误", f"启动失败: {str(e)}")
            self.status_var.set("就绪")

    def run_bot(self):
        """运行游戏机器人主循环"""
        try:
            # 运行主循环，直到达到指定次数或被停止
            while self.bot and self.bot.running:
                # 运行一次主循环迭代
                self.bot.main_loop(iterations=1)
                # 短暂休眠，避免CPU占用过高
                time.sleep(0.1)
        except Exception as e:
            print(f"运行出错: {str(e)}")
        finally:
            # 停止运行
            self.root.after(0, self.stop_bot)

    def stop_bot(self):
        """停止游戏机器人"""
        if self.bot:
            self.bot.running = False
            self.bot = None

        # 更新状态
        self.status_var.set("已停止")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def quit_app(self):
        """退出应用程序"""
        if self.bot:
            self.bot.running = False
        self.root.quit()


if __name__ == "__main__":
    # 创建主窗口
    root = tk.Tk()

    # 设置窗口图标（可选）
    try:
        root.iconbitmap(default=None)
    except:
        pass

    # 创建GUI实例
    app = GameBotGUI(root)

    # 运行主循环
    root.mainloop()

# 使用说明:
# 1. 安装必要的依赖: pip install pyautogui opencv-python pillow pynput pywin32
# 2. 替换脚本中的游戏窗口标题为你的游戏窗口标题
# 3. 在 templates 文件夹中添加游戏界面元素的截图作为模板
# 4. 运行脚本: python game_bot.py
# 5. 脚本会自动查找游戏窗口，开始战斗，收集奖励
#
# 注意事项:
# - 本脚本仅提供基础框架，需要根据具体游戏进行调整
# - 为了提高识别准确率，建议使用游戏窗口的原始分辨率
# - 使用时请确保游戏窗口未被遮挡
# - 可以通过添加更多的模板和状态判断来提高脚本的智能性
# - 游戏过程中尽量不要操作鼠标和键盘，以免干扰脚本运行

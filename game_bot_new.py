import os
import time
import cv2
import numpy as np
import pyautogui


class FastGameBot:
    def __init__(self, game_title=None, battle_time=0, battle_count=0, mode=0, priority_skills=None, template_dir="templates"):
        # ✅ 完全兼容你原来的 GameBot 初始化参数
        self.game_title = game_title
        self.battle_time = battle_time
        self.battle_count = battle_count
        self.mode = mode

        self.template_dir = template_dir
        self.template_cache = {}

        self.current_img = None  # ✅ 当前帧缓存
        self.game_window = None

        # ✅ 控制运行（默认True，兼容你GUI线程）
        self.running = True

        # ✅ 技能优先级
        self.priority_skills = priority_skills if priority_skills else []

    # =========================
    # 截图（只在一轮内截一次）
    # =========================
    def capture_frame(self):
        if self.current_img is None:
            screenshot = pyautogui.screenshot(region=self.game_window)
            self.current_img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        return self.current_img

    # =========================
    # 模板缓存
    # =========================
    def get_template(self, name):
        if name not in self.template_cache:
            path = os.path.join(self.template_dir, name)
            template = cv2.imread(path)
            if template is None:
                return None
            self.template_cache[name] = template
        return self.template_cache[name]

    # =========================
    # 模板匹配（使用缓存帧🔥）
    # =========================
    def match_template(self, template, threshold=0.8):
        img = self.capture_frame()
        result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            h, w = template.shape[:2]
            return (max_loc[0] + w//2, max_loc[1] + h//2)
        return None

    # =========================
    # 单模板查找（完全兼容你原 find_template🔥）
    # =========================
    def find_template(self, template_name, threshold=0.8):
        template = self.get_template(template_name)
        if template is None:
            return None

        pos = self.match_template(template, threshold)
        if pos:
            return pos
        return None

    # =========================
    # 技能识别（完全兼容你原逻辑🔥）
    # =========================
    def find_skill(self):
        # 优先技能
        for skill_templates in self.priority_skills:
            for template in skill_templates:
                if not template.endswith('.png'):
                    template += '.png'
                pos = self.find_template(template)
                if pos:
                    self.click(*pos)
                    time.sleep(0.2)
                    return True
        return False

    # =========================
    # 点击
    # =========================
    def click(self, x, y):
        pyautogui.moveTo(x, y, duration=0)
        pyautogui.click()

    # =========================
    # 主循环（完全兼容你GUI🔥）
    # =========================
    def main_loop(self, iterations=None):
        count = 0

        while self.running:
            if iterations and count >= iterations:
                break

            start = time.time()

            # ✅ 每一轮清空帧缓存（关键！）
            self.current_img = None

            # ✅ 你的原逻辑：随便调用 find_xxx 都不会重复截图
            self.find_skill()

            count += 1

            # 控制帧率
            cost = time.time() - start
            time.sleep(max(0.03 - cost, 0))


# =========================
# 使用方式（完全不改你GUI代码）
# =========================
# self.bot = FastGameBot(...)
# self.bot.main_loop(iterations=1)
# self.bot.running = False

# ------------------------------------------------------------------------
# rect07_lcd.py
# 基于 rect_07_1.py 的 LCD 彩色输出版本：
# 1. 摄像头采集 RGB565 彩色图像，用于 LCD 彩色预览。
# 2. 每帧 copy() 一份图像转灰度后，在灰度副本上执行 ROI 二值化、形态学滤波和矩形查找。
# 3. 识别结果绘制回彩色原图，保留 rect_07 的动态 ROI 跟踪、丢失滑行和 GPIO2 有效目标输出。
# ------------------------------------------------------------------------
import time, os, gc, sys, math
import image

from media.sensor import *
from media.display import *
from media.media import *
from machine import Pin
from machine import FPIOA

# --- 摄像头视场角 (FOV) 预估值 ---
H_FOV_DEG = 60.0
V_FOV_DEG = 35.0

# 预计算 FOV 相关的常数
H_TAN_HALF_FOV = math.tan(math.radians(H_FOV_DEG / 2.0))
V_TAN_HALF_FOV = math.tan(math.radians(V_FOV_DEG / 2.0))

# 1. 严格同步跑通的分辨率设置
DETECT_WIDTH = ALIGN_UP(320, 16)
DETECT_HEIGHT = 240
LCD_WIDTH = 800
LCD_HEIGHT = 480
LCD_X_SCALE = LCD_WIDTH / DETECT_WIDTH
LCD_Y_SCALE = LCD_HEIGHT / DETECT_HEIGHT

IMG_CENTER_X = DETECT_WIDTH // 2
IMG_CENTER_Y = DETECT_HEIGHT // 2

# 用户要求的二值化阈值
target_threshold = (53, 175)

# --- 状态机定义 ---
STATE_SEARCHING = 0
STATE_LOCKED = 1
STATE_COASTING = 2

# --- 靶标验证与局部 ROI 追踪配置 ---
MIN_ASPECT_RATIO = 1.1
MAX_ASPECT_RATIO = 1.8
MIN_AREA = 3000
MAX_AREA = 35000
MIN_DENSITY_MEAN = 170

# ROI 局部追踪参数
ROI_MARGIN = 25
MAX_COASTING_FRAMES = 3

sensor = None
gpio2_pin = None

def gpio_init():
    global gpio2_pin
    fpioa = FPIOA()
    fpioa.set_function(2, FPIOA.GPIO2)
    gpio2_pin = Pin(2, Pin.OUT, pull=Pin.PULL_NONE, drive=7)
    gpio2_pin.value(0)

def set_gpio2_high(is_high):
    if gpio2_pin:
        gpio2_pin.value(1 if is_high else 0)

def camera_init():
    global sensor
    # 构造 Sensor 对象
    sensor = Sensor(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    sensor.reset()

    # set chn0 output size
    sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    # set chn0 output format (彩色预览)
    sensor.set_pixformat(Sensor.RGB565)

    # use LCD as display output
    Display.init(Display.ST7701, width=LCD_WIDTH, height=LCD_HEIGHT, fps=100, to_ide=False)
    # init media manager
    MediaManager.init()
    # sensor start run
    sensor.run()
    gpio_init()

def camera_deinit():
    global sensor
    set_gpio2_high(False)
    if sensor:
        sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    MediaManager.deinit()

# ------------------------------------------------------------------------
# 坐标解算辅助函数 (采用投影交点法)
# ------------------------------------------------------------------------
def get_target_center(corners):
    x1, y1 = corners[0]; x2, y2 = corners[2]
    x3, y3 = corners[1]; x4, y4 = corners[3]
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 0.0001:
        return (x1 + x2 + x3 + x4) // 4, (y1 + y2 + y3 + y4) // 4
    ix = ((x1*y2 - y1*x2)*(x3 - x4) - (x1 - x2)*(x3*y4 - y3*x4)) // denom
    iy = ((x1*y2 - y1*x2)*(y3 - y4) - (y1 - y2)*(x3*y4 - y3*x4)) // denom
    return int(ix), int(iy)

# ------------------------------------------------------------------------
# 校验单个矩形是否符合靶标特征 (几何 + 占比过滤)
# ------------------------------------------------------------------------
def validate_target_candidate(img_algo, r):
    w, h = r.w(), r.h()
    area = w * h
    aspect_ratio = float(w) / h if h != 0 else 0

    if not (MIN_ASPECT_RATIO <= aspect_ratio <= MAX_ASPECT_RATIO):
        return False
    if not (MIN_AREA <= area <= MAX_AREA):
        return False

    stat = img_algo.statistics(roi=r.rect())
    if stat.mean() < MIN_DENSITY_MEAN:
        return False

    return True

# ------------------------------------------------------------------------
# 根据检测到的矩形，计算并裁剪下一帧的局部搜索 ROI
# ------------------------------------------------------------------------
def calculate_search_roi(r):
    rx, ry, rw, rh = r.rect()

    x = rx - ROI_MARGIN
    y = ry - ROI_MARGIN
    w = rw + 2 * ROI_MARGIN
    h = rh + 2 * ROI_MARGIN

    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(DETECT_WIDTH, x + w)
    y2 = min(DETECT_HEIGHT, y + h)

    return [x1, y1, x2 - x1, y2 - y1]

def capture_picture():
    # --- 瞬时帧率计算变量 (滑动窗口，以1秒为区间统计真实帧率) ---
    frame_times = []
    fps_val = 0.0

    # --- 追踪状态与 ROI 缓存变量 ---
    tracking_state = STATE_SEARCHING
    coast_counter = 0

    # 初始状态下的追踪区域为全图
    search_roi = [0, 0, DETECT_WIDTH, DETECT_HEIGHT]

    # 缓存的历史解算数据 (用于丢失滑行输出)
    last_rect = None
    last_cx = 0
    last_cy = 0
    last_dx = 0
    last_dy = 0
    last_yaw = 0.0
    last_pitch = 0.0
    display_img = image.Image(LCD_WIDTH, LCD_HEIGHT, image.RGB565)

    while True:
        # 计算滑动窗口瞬时帧率
        now_time = time.ticks_ms()
        frame_times.append(now_time)
        while frame_times and time.ticks_diff(now_time, frame_times[0]) > 1000:
            frame_times.pop(0)

        if len(frame_times) > 1:
            fps_val = (len(frame_times) - 1) * 1000.0 / time.ticks_diff(now_time, frame_times[0])
        else:
            fps_val = 0.0

        try:
            os.exitpoint()
            global sensor
            # 1. 抓取彩色原图
            img = sensor.snapshot()

            # 2. 复制一份灰度算法图，避免在彩色预览图上做破坏性处理
            img_algo = img.copy().to_grayscale()

            # 对局部/全局搜索区域进行二值化
            img_algo.binary([target_threshold], roi=search_roi)

            # 在同一搜索区域执行形态学滤波
            img_algo.dilate(1, roi=search_roi)
            img_algo.erode(1, roi=search_roi)

            # 运行矩形识别，同样只限制在搜索区域内
            rects = img_algo.find_rects(threshold=8000, roi=search_roi)

            best_rect = None

            if rects:
                valid_candidates = []
                for r in rects:
                    if validate_target_candidate(img_algo, r):
                        valid_candidates.append(r)

                if valid_candidates:
                    best_rect = max(valid_candidates, key=lambda r: r.w() * r.h())

            # 3. 状态机逻辑处理与 ROI 动态更新
            if best_rect is not None:
                set_gpio2_high(True)
                tracking_state = STATE_LOCKED
                coast_counter = 0

                search_roi = calculate_search_roi(best_rect)

                corners = best_rect.corners()
                t_cx, t_cy = get_target_center(corners)

                dx = t_cx - IMG_CENTER_X
                dy = t_cy - IMG_CENTER_Y

                angle_x_rad = math.atan((dx / (DETECT_WIDTH / 2.0)) * H_TAN_HALF_FOV)
                angle_y_rad = math.atan((dy / (DETECT_HEIGHT / 2.0)) * V_TAN_HALF_FOV)

                yaw_angle = math.degrees(angle_x_rad)
                pitch_angle = math.degrees(angle_y_rad)

                # 绘制到彩色原图
                img.draw_rectangle([v for v in best_rect.rect()], color=(255, 0, 0), thickness=2)
                img.draw_cross(t_cx, t_cy, color=(0, 0, 255), size=15)
                img.draw_rectangle(search_roi, color=(0, 255, 0), thickness=1)

                img.draw_cross(IMG_CENTER_X, IMG_CENTER_Y, color=(255, 255, 0), size=10)
                img.draw_line(IMG_CENTER_X, IMG_CENTER_Y, t_cx, t_cy, color=(255, 255, 255))
                img.draw_string(t_cx + 10, t_cy + 10, "dx:%d dy:%d" % (dx, dy), color=(255, 255, 255), scale=2)
                img.draw_string(t_cx + 10, t_cy + 30, "Yaw:%.1f Pitch:%.1f" % (yaw_angle, pitch_angle), color=(255, 255, 0), scale=2)

                last_rect = [v for v in best_rect.rect()]
                last_cx, last_cy = t_cx, t_cy
                last_dx, last_dy = dx, dy
                last_yaw, last_pitch = yaw_angle, pitch_angle

                print(f"Target LOCKED (Color ROI) -> dx: {dx:3d}, dy: {dy:3d} | Yaw: {yaw_angle:5.1f}°, Pitch: {pitch_angle:5.1f}° | ROI: {search_roi} | FPS: {fps_val:.1f}")

            else:
                set_gpio2_high(False)
                if tracking_state == STATE_LOCKED:
                    tracking_state = STATE_COASTING
                    coast_counter = MAX_COASTING_FRAMES
                elif tracking_state == STATE_COASTING:
                    coast_counter -= 1
                    if coast_counter <= 0:
                        tracking_state = STATE_SEARCHING
                        search_roi = [0, 0, DETECT_WIDTH, DETECT_HEIGHT]

                if tracking_state == STATE_COASTING:
                    img.draw_rectangle(last_rect, color=(255, 0, 0), thickness=2)
                    img.draw_cross(last_cx, last_cy, color=(0, 0, 255), size=15)
                    img.draw_rectangle(search_roi, color=(0, 255, 0), thickness=1)

                    img.draw_cross(IMG_CENTER_X, IMG_CENTER_Y, color=(255, 255, 0), size=10)
                    img.draw_line(IMG_CENTER_X, IMG_CENTER_Y, last_cx, last_cy, color=(255, 255, 255))
                    img.draw_string(last_cx + 10, last_cy + 10, "dx:%d dy:%d (Coast)" % (last_dx, last_dy), color=(255, 255, 255), scale=2)
                    img.draw_string(last_cx + 10, last_cy + 30, "Yaw:%.1f Pitch:%.1f" % (last_yaw, last_pitch), color=(255, 255, 0), scale=2)

                    print(f"Target Coasting [{coast_counter}] -> Keep ROI: {search_roi} | FPS: {fps_val:.1f}")
                else:
                    img.draw_string(10, 40, "Searching Fullscreen...", color=(255, 255, 0), scale=2)
                    print(f"Target Searching Fullscreen... | FPS: {fps_val:.1f}")

            # 4. 绘制 FPS
            img.draw_string(10, 10, "FPS: %.2f" % fps_val, color=(255, 255, 0), scale=2)

            # 5. 显示 LCD 全屏彩色预览
            display_img.clear()
            display_img.draw_image(img, 0, 0, x_scale=LCD_X_SCALE, y_scale=LCD_Y_SCALE)
            Display.show_image(display_img)

            # 6. 内存回收
            del img_algo
            img = None
            gc.collect()

        except KeyboardInterrupt as e:
            print("user stop")
            break
        except BaseException as e:
            import sys
            sys.print_exception(e)
            break

def main():
    os.exitpoint(os.EXITPOINT_ENABLE)
    camera_is_init = False
    try:
        print("--- rect07_lcd 启动 (动态局部 ROI LCD 彩色输出版) ---")
        camera_init()
        camera_is_init = True
        print("camera capture start with color preview recognition")
        capture_picture()
    except Exception as e:
        import sys
        sys.print_exception(e)
    finally:
        if camera_is_init:
            print("camera deinit")
            camera_deinit()

if __name__ == "__main__":
    main()

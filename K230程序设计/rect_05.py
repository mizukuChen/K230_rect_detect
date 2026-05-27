# ------------------------------------------------------------------------
# rect_05.py
# 基于 rect_04.py (形态学滤波版) 的进阶时空连续性优化 (方案三)：
# 1. 引入帧间灰度差分标准差 (Stdev) 评估图像信息量变化量。
# 2. 如果连续两帧变化极小且已经锁定目标，则跳过耗时的形态学滤波和矩形搜索，直接复用缓存数据。
# 3. 实现了高精度、高帧率与极高防抖稳定性的双重提升。
# ------------------------------------------------------------------------
import time, os, gc, sys, math

from media.sensor import *
from media.display import *
from media.media import *

# --- 摄像头视场角 (FOV) 预估值 ---
H_FOV_DEG = 60.0
V_FOV_DEG = 35.0

# 预计算 FOV 相关的常数
H_TAN_HALF_FOV = math.tan(math.radians(H_FOV_DEG / 2.0))
V_TAN_HALF_FOV = math.tan(math.radians(V_FOV_DEG / 2.0))

# 1. 严格同步跑通的分辨率设置
DETECT_WIDTH = ALIGN_UP(320, 16)
DETECT_HEIGHT = 240

IMG_CENTER_X = DETECT_WIDTH // 2
IMG_CENTER_Y = DETECT_HEIGHT // 2

# 用户要求的二值化阈值
target_threshold = (66, 163)

# --- 时空差分防抖阈值 ---
# 图像差分标准差阈值，用于评估图像中是否有显著运动或新信息。
# 如果两帧差异的标准差低于该值，且之前已锁定目标，则认为图像静止，跳过算法计算。
# 可以根据现场实际噪声大小进行微调（建议范围：3.0 ~ 5.0）。
STDEV_THRESHOLD = 3.5

# --- 空间门限与状态机防突变配置 (方案一) ---
MAX_DISPLACEMENT = 60      # 两帧之间允许的最大像素位移，超过则认为是背景噪点
MAX_COASTING_FRAMES = 3    # 目标短暂丢失时的最大容忍/维持帧数

STATE_SEARCHING = 0
STATE_LOCKED = 1
STATE_COASTING = 2

sensor = None

def camera_init():
    global sensor
    # 构造 Sensor 对象
    sensor = Sensor(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    sensor.reset()

    # set chn0 output size
    sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    # set chn0 output format (纯灰度极速)
    sensor.set_pixformat(Sensor.GRAYSCALE)

    # use IDE as display output
    Display.init(Display.VIRT, width=DETECT_WIDTH, height=DETECT_HEIGHT, fps=100, to_ide=True)
    # init media manager
    MediaManager.init()
    # sensor start run
    sensor.run()

def camera_deinit():
    global sensor
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

def capture_picture():
    fps = time.clock()
    
    # --- 初始化时空缓存变量 ---
    prev_img = None       # 保存上一帧的原始灰度拷贝
    tracking_state = STATE_SEARCHING
    coast_counter = 0
    last_rect = None      # 上一次检测到的矩形框坐标 [x, y, w, h]
    last_cx = 0           # 上一次的目标中心 x
    last_cy = 0           # 上一次的目标中心 y
    last_dx = 0           # 上一次的中心偏差 dx
    last_dy = 0           # 上一次的中心偏差 dy
    last_yaw = 0.0        # 上一次解算出的 Yaw 偏角
    last_pitch = 0.0      # 上一次解算出的 Pitch 偏角

    while True:
        fps.tick()
        try:
            os.exitpoint()
            global sensor
            # 1. 抓取图像 (原始灰度图)
            img = sensor.snapshot()

            # 备份当前帧作为下一次的对比图（必须在二值化等破坏性原位操作之前复制）
            prev_img_temp = img.copy()

            skip_algo = False
            stdev = 0.0

            # 2. 时空连续性评估：计算与上一帧的差分标准差
            if prev_img is not None:
                diff_img = img.copy()
                diff_img.difference(prev_img)
                stdev = diff_img.statistics().stdev()
                del diff_img
                
                # 如果变化量低于阈值，且当前处于锁定状态，则跳过算法计算
                if stdev < STDEV_THRESHOLD and tracking_state == STATE_LOCKED:
                    skip_algo = True

            # 3. 运行识别流程
            if skip_algo:
                # 依然执行快速二值化以维持画面风格的一致性 (防止画面闪烁)
                img.binary([target_threshold])
                
                # 直接使用上一帧缓存的坐标和框线进行绘制
                img.draw_rectangle(last_rect, color=255, thickness=2)
                img.draw_cross(last_cx, last_cy, color=255, size=15)
                img.draw_cross(IMG_CENTER_X, IMG_CENTER_Y, color=255, size=10)
                img.draw_line(IMG_CENTER_X, IMG_CENTER_Y, last_cx, last_cy, color=255)

                img.draw_string(last_cx + 10, last_cy + 10, "dx:%d dy:%d (Cached)" % (last_dx, last_dy), color=255, scale=2)
                img.draw_string(last_cx + 10, last_cy + 30, "Yaw:%.1f Pitch:%.1f (Cached)" % (last_yaw, last_pitch), color=255, scale=2)

                print(f"Target Found (Cached) -> dx: {last_dx:3d}, dy: {last_dy:3d} | Yaw: {last_yaw:5.1f}°, Pitch: {last_pitch:5.1f}° | Stdev: {stdev:.2f}")

            else:
                # 正常应用二值化
                img.binary([target_threshold])

                # --- 形态学滤波 (闭运算) ---
                img.dilate(1)
                img.erode(1)

                # 运行矩形识别逻辑
                rects = img.find_rects(threshold=8000)

                best_rect = None
                
                if rects:
                    if tracking_state == STATE_SEARCHING:
                        # 搜寻模式：信任画面中最大的矩形
                        best_rect = max(rects, key=lambda r: r.w() * r.h())
                    else:
                        # 锁定/维持模式：寻找距离上一帧位置在 MAX_DISPLACEMENT 以内且最近的矩形
                        min_dist = 99999
                        for r in rects:
                            corners = r.corners()
                            cx, cy = get_target_center(corners)
                            dist = math.sqrt((cx - last_cx)**2 + (cy - last_cy)**2)
                            if dist <= MAX_DISPLACEMENT and dist < min_dist:
                                min_dist = dist
                                best_rect = r

                if best_rect is not None:
                    # --- 成功找到并确认目标 ---
                    tracking_state = STATE_LOCKED
                    coast_counter = 0

                    corners = best_rect.corners()
                    t_cx, t_cy = get_target_center(corners)
                    
                    dx = t_cx - IMG_CENTER_X
                    dy = t_cy - IMG_CENTER_Y

                    angle_x_rad = math.atan((dx / (DETECT_WIDTH / 2.0)) * H_TAN_HALF_FOV)
                    angle_y_rad = math.atan((dy / (DETECT_HEIGHT / 2.0)) * V_TAN_HALF_FOV)

                    yaw_angle = math.degrees(angle_x_rad)
                    pitch_angle = math.degrees(angle_y_rad)

                    # 绘制
                    img.draw_rectangle([v for v in best_rect.rect()], color=255, thickness=2)
                    img.draw_cross(t_cx, t_cy, color=255, size=15)
                    img.draw_cross(IMG_CENTER_X, IMG_CENTER_Y, color=255, size=10)
                    img.draw_line(IMG_CENTER_X, IMG_CENTER_Y, t_cx, t_cy, color=255)

                    img.draw_string(t_cx + 10, t_cy + 10, "dx:%d dy:%d" % (dx, dy), color=255, scale=2)
                    img.draw_string(t_cx + 10, t_cy + 30, "Yaw:%.1f Pitch:%.1f" % (yaw_angle, pitch_angle), color=255, scale=2)

                    # 缓存最新状态
                    last_rect = [v for v in best_rect.rect()]
                    last_cx, last_cy = t_cx, t_cy
                    last_dx, last_dy = dx, dy
                    last_yaw, last_pitch = yaw_angle, pitch_angle

                    print(f"Target Locked -> dx: {dx:3d}, dy: {dy:3d} | Yaw: {yaw_angle:5.1f}°, Pitch: {pitch_angle:5.1f}° | Stdev: {stdev:.2f}")
                else:
                    # --- 画面无目标或目标均在门限外 (噪点突变) ---
                    if tracking_state == STATE_LOCKED:
                        tracking_state = STATE_COASTING
                        coast_counter = MAX_COASTING_FRAMES
                    elif tracking_state == STATE_COASTING:
                        coast_counter -= 1
                        if coast_counter <= 0:
                            tracking_state = STATE_SEARCHING
                    
                    if tracking_state == STATE_COASTING:
                        # 惯性滑行 (Coast) 状态：使用上一帧的缓存参数顶替
                        img.draw_rectangle(last_rect, color=255, thickness=2)
                        img.draw_cross(last_cx, last_cy, color=255, size=15)
                        img.draw_cross(IMG_CENTER_X, IMG_CENTER_Y, color=255, size=10)
                        img.draw_line(IMG_CENTER_X, IMG_CENTER_Y, last_cx, last_cy, color=255)

                        img.draw_string(last_cx + 10, last_cy + 10, "dx:%d dy:%d (Coast)" % (last_dx, last_dy), color=255, scale=2)
                        img.draw_string(last_cx + 10, last_cy + 30, "Yaw:%.1f Pitch:%.1f (Coast)" % (last_yaw, last_pitch), color=255, scale=2)
                        
                        print(f"Target Coasting [{coast_counter}] -> dx: {last_dx:3d}, dy: {last_dy:3d} | Stdev: {stdev:.2f}")
                    else:
                        print(f"Target Searching... | Stdev: {stdev:.2f}")

            # 4. 绘制 FPS 到屏幕
            img.draw_string(10, 10, "FPS: %.2f" % fps.fps(), color=255, scale=2)

            # 5. 显示到屏幕
            Display.show_image(img)

            # 6. 状态迭代与内存释放
            if prev_img is not None:
                del prev_img
            prev_img = prev_img_temp  # 转移最新的原始灰度拷贝

            del img
            gc.collect()

            # print(f"FPS: {fps.fps():.2f}")

        except KeyboardInterrupt as e:
            print("user stop")
            break
        except BaseException as e:
            import sys
            sys.print_exception(e)
            break

    # 循环退出后释放最终残留的对比图
    if prev_img is not None:
        del prev_img

def main():
    os.exitpoint(os.EXITPOINT_ENABLE)
    camera_is_init = False
    try:
        print("--- rect_05 启动 (时空差分防抖版) ---")
        camera_init()
        camera_is_init = True
        print("camera capture start with recognition")
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

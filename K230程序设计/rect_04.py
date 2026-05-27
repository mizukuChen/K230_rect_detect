# ------------------------------------------------------------------------
# rect_04.py
# 基于 main.py (灰度极速版) 的进阶优化：
# 1. 增加形态学滤波 (闭运算：先膨胀后腐蚀) 提高边缘稳定性
# 2. 增加“最大面积”过滤，只追踪主目标，过滤背景噪点
# ------------------------------------------------------------------------
import time, os, gc, sys, math

from media.sensor import *
from media.display import *
from media.media import *

# --- [新增] 摄像头视场角 (FOV) 预估值 ---
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
    while True:
        fps.tick()
        try:
            os.exitpoint()
            global sensor
            # 1. 抓取图像
            img = sensor.snapshot()

            # 2. 应用二值化
            img.binary([target_threshold])

            # --- [新增] 3. 形态学滤波 (闭运算) ---
            # 先膨胀 (dilate)：把断裂的黑色边框连接起来，消除白色小孔洞
            img.dilate(1)
            # 再腐蚀 (erode)：把膨胀导致变粗的边框恢复原样，消除边缘毛刺
            img.erode(1)

            # 4. 矩形识别逻辑
            # 由于图像已经被极大地平滑了，threshold 可以适当降低以增强识别率
            rects = img.find_rects(threshold = 8000)

            if rects:
                # --- [新增] 寻找面积最大的矩形 ---
                max_rect = max(rects, key=lambda r: r.w() * r.h())

                corners = max_rect.corners()
                t_cx, t_cy = get_target_center(corners)

                # 计算中心偏差
                dx = t_cx - IMG_CENTER_X
                dy = t_cy - IMG_CENTER_Y

                # --- 计算偏转角度 (Yaw / Pitch) ---
                angle_x_rad = math.atan((dx / (DETECT_WIDTH / 2.0)) * H_TAN_HALF_FOV)
                angle_y_rad = math.atan((dy / (DETECT_HEIGHT / 2.0)) * V_TAN_HALF_FOV)

                yaw_angle = math.degrees(angle_x_rad)
                pitch_angle = math.degrees(angle_y_rad)

                # 在二值图上绘制 (255 为白色)
                img.draw_rectangle([v for v in max_rect.rect()], color = 255, thickness=2)
                # 绘制目标中心十字
                img.draw_cross(t_cx, t_cy, color=255, size=15)
                # 绘制屏幕参考中心十字 (较小)
                img.draw_cross(IMG_CENTER_X, IMG_CENTER_Y, color=255, size=10)
                # 绘制中心连线 (显示距离感)
                img.draw_line(IMG_CENTER_X, IMG_CENTER_Y, t_cx, t_cy, color=255)

                # 直接在图像上写出距离和角度数值
                img.draw_string(t_cx + 10, t_cy + 10, "dx:%d dy:%d" % (dx, dy), color=255, scale=1.5)
                img.draw_string(t_cx + 10, t_cy + 30, "dY:%.1f dP:%.1f" % (yaw_angle, pitch_angle), color=255, scale=1.5)

                print(f"Target Found -> dx: {dx:3d}, dy: {dy:3d} | Yaw: {yaw_angle:5.1f}°, Pitch: {pitch_angle:5.1f}° | Area: {max_rect.w()*max_rect.h()}")

            # 绘制 FPS
            img.draw_string(10, 10, "FPS: %.2f" % fps.fps(), color=255, scale=2)

            # 5. 显示到屏幕
            Display.show_image(img)

            # 6. 显式释放
            img = None
            gc.collect()

            # 打印 FPS 确认负载
            print(f"FPS: {fps.fps():.2f}")

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
        print("--- rect_04 启动 (形态学滤波版) ---")
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

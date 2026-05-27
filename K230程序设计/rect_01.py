# Find Rects Example
#
# This example shows off how to find rectangles in the image using the quad threshold
# detection code from our April Tags code. The quad threshold detection algorithm
# detects rectangles in an extremely robust way and is much better than Hough
# Transform based methods. For example, it can still detect rectangles even when lens
# distortion causes those rectangles to look bent. Rounded rectangles are no problem!
# (But, given this the code will also detect small radius circles too)...
import time, os, gc, sys, math

from media.sensor import *
from media.display import *
from media.media import *

DETECT_WIDTH = ALIGN_UP(320, 16)
DETECT_HEIGHT = 240

# --- [新增] 摄像头视场角 (FOV) 预估值 ---
# 根据 GC2093/常见模组特性，假设水平 FOV 约 65 度，垂直 FOV 约 50 度
# 比赛时需要根据实际摄像头参数或实测进行修改
H_FOV_DEG = 60.0
V_FOV_DEG = 35.0

# 预计算 FOV 相关的常数，避免在循环中重复计算 (提升帧率)
# math.tan 接收弧度
H_TAN_HALF_FOV = math.tan(math.radians(H_FOV_DEG / 2.0))
V_TAN_HALF_FOV = math.tan(math.radians(V_FOV_DEG / 2.0))

sensor = None

def camera_init():
    global sensor

    # construct a Sensor object with default configure
    sensor = Sensor(width=DETECT_WIDTH,height=DETECT_HEIGHT)
    # sensor reset
    sensor.reset()
    # set hmirror
    # sensor.set_hmirror(False)
    # sensor vflip
    # sensor.set_vflip(False)

    # set chn0 output size
    sensor.set_framesize(width=DETECT_WIDTH,height=DETECT_HEIGHT)
    # set chn0 output format
    sensor.set_pixformat(Sensor.RGB565)

    # use IDE as display output
    Display.init(Display.VIRT, width= DETECT_WIDTH, height = DETECT_HEIGHT,fps=100,to_ide = True)
    # init media manager
    MediaManager.init()
    # sensor start run
    sensor.run()

def camera_deinit():
    global sensor
    # sensor stop run
    sensor.stop()
    # deinit display
    Display.deinit()
    # sleep
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    # release media buffer
    MediaManager.deinit()

def get_target_center(corners):
    """采用投影交点法计算中心"""
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
    # 定义二值化阈值
    GRAYSCALE_THRESHOLD = [(66, 163)]

    # 画面中心
    IMG_CENTER_X = DETECT_WIDTH // 2
    IMG_CENTER_Y = DETECT_HEIGHT // 2

    while True:
        fps.tick()
        try:
            os.exitpoint()
            global sensor
            # 1. 抓取彩色原图
            img = sensor.snapshot()

            # 2. Copy 一份图像并处理为黑白二值化，用于识别
            img_algo = img.copy().to_grayscale()
            img_algo.binary(GRAYSCALE_THRESHOLD)

            # 3. 在黑白副本 img_algo 上运行识别算法
            rects = img_algo.find_rects(threshold = 10000)

            if rects:
                # --- [新增逻辑] 寻找面积最大的矩形 ---
                # r.w() * r.h() 即为矩形面积
                max_rect = max(rects, key=lambda r: r.w() * r.h())

                # 只对最大的矩形进行解算
                corners = max_rect.corners()
                t_cx, t_cy = get_target_center(corners)
                # 计算中心偏差 (像素)
                dx = t_cx - IMG_CENTER_X
                dy = t_cy - IMG_CENTER_Y

                # --- [新增] 计算偏转角度 (Yaw / Pitch) ---
                # math.atan 返回弧度，用 math.degrees 转换为角度
                # 注意：这里假设画面中心偏差与角度存在正切关系
                angle_x_rad = math.atan((dx / (DETECT_WIDTH / 2.0)) * H_TAN_HALF_FOV)
                angle_y_rad = math.atan((dy / (DETECT_HEIGHT / 2.0)) * V_TAN_HALF_FOV)

                yaw_angle = math.degrees(angle_x_rad)
                pitch_angle = math.degrees(angle_y_rad)

                # --- 4. 将识别结果绘制在【彩色原图 img】上 ---
                img.draw_rectangle([v for v in max_rect.rect()], color = (255, 0, 0), thickness=2)
                img.draw_cross(t_cx, t_cy, color=(0, 0, 255), size=15)
                img.draw_cross(IMG_CENTER_X, IMG_CENTER_Y, color=(255, 255, 0), size=10)
                img.draw_line(IMG_CENTER_X, IMG_CENTER_Y, t_cx, t_cy, color=(255, 255, 255))
                img.draw_string(t_cx + 10, t_cy + 10, "dx:%d dy:%d" % (dx, dy), color=(255, 255, 255), scale=2)
                img.draw_string(t_cx + 10, t_cy + 30, "Yaw:%.1f Pitch:%.1f" % (yaw_angle, pitch_angle), color=(255, 255, 0), scale=2)

                print(f"Target Found -> dx: {dx:3d}, dy: {dy:3d} | Yaw: {yaw_angle:5.1f}°, Pitch: {pitch_angle:5.1f}°")
            # 5. 在 IDE 中显示彩色原图
            Display.show_image(img)

            # 6. 显式释放资源
            del img_algo
            img = None

            gc.collect()
            print(f"FPS: {fps.fps():.2f}")
        except KeyboardInterrupt as e:
            print("user stop: ", e)
            break
        except BaseException as e:
            import sys
            sys.print_exception(e)
            break

def main():
    os.exitpoint(os.EXITPOINT_ENABLE)
    camera_is_init = False
    try:
        print("camera init")
        camera_init()
        camera_is_init = True
        print("camera capture")
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

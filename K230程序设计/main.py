# ------------------------------------------------------------------------
# rect_03.py
# 在跑通的 test_no_algo.py (官方例程模板) 基础上增加矩形识别
# ------------------------------------------------------------------------
import time, os, gc, sys

from media.sensor import *
from media.display import *
from media.media import *

# 1. 严格同步跑通的分辨率设置
DETECT_WIDTH = ALIGN_UP(640, 16)
DETECT_HEIGHT = 480

IMG_CENTER_X = DETECT_WIDTH // 2
IMG_CENTER_Y = DETECT_HEIGHT // 2

# 用户要求的阈值
target_threshold = (66, 163)

sensor = None

def camera_init():
    global sensor
    # 构造 Sensor 对象 (遵循跑通的 test_no_algo.py 配置)
    sensor = Sensor(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    sensor.reset()

    # set chn0 output size
    sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    # set chn0 output format
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
            
            # 3. 【新增】矩形识别逻辑
            # 由于图像已经是纯黑白(二值图)，算法运行速度会非常快
            for r in img.find_rects(threshold = 10000):
                corners = r.corners()
                t_cx, t_cy = get_target_center(corners)
                
                # 计算中心偏差
                dx = t_cx - IMG_CENTER_X
                dy = t_cy - IMG_CENTER_Y
                
                # 在二值图上绘制 (255 为白色)
                img.draw_rectangle([v for v in r.rect()], color = 255, thickness=2)
                # 绘制目标中心十字
                img.draw_cross(t_cx, t_cy, color=255, size=15)
                # 绘制屏幕参考中心十字 (较小)
                img.draw_cross(IMG_CENTER_X, IMG_CENTER_Y, color=255, size=10)
                # 绘制中心连线 (显示距离感)
                img.draw_line(IMG_CENTER_X, IMG_CENTER_Y, t_cx, t_cy, color=255)
                
                # 直接在图像上写出距离数值
                img.draw_string(t_cx + 10, t_cy + 10, "dx:%d dy:%d" % (dx, dy), color=255, scale=2)
                
                print(f"Target Found -> dx: {dx}, dy: {dy}")

            # 4. 显示到屏幕
            Display.show_image(img)

            # 5. 显式释放 (严格遵循跑通的版本)
            del img
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
        print("camera init")
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

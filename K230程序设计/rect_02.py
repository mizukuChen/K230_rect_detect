# ------------------------------------------------------------------------
# rect_02.py (稳定识别版 + 彩色 IDE 预览)
# ------------------------------------------------------------------------
# 结合了 03 的稳定性逻辑，并恢复了彩色预览功能
# ------------------------------------------------------------------------
import time, os, gc, sys

from media.sensor import *
from media.display import *
from media.media import *

# 1. 分辨率设置 (ALIGN_UP 确保硬件内存对齐)
DETECT_WIDTH = ALIGN_UP(640, 16)
DETECT_HEIGHT = 480

IMG_CENTER_X = DETECT_WIDTH // 2
IMG_CENTER_Y = DETECT_HEIGHT // 2

# 用户要求的阈值 (66, 163)
target_threshold = (66, 163)

sensor = None

def camera_init():
    global sensor
    try: MediaManager.deinit()
    except: pass
    
    # 构造 Sensor
    sensor = Sensor(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    sensor.reset()

    # --- 恢复彩色采集 ---
    sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    sensor.set_pixformat(Sensor.RGB565) 

    # 初始化 IDE 虚拟显示
    Display.init(Display.VIRT, width=DETECT_WIDTH, height=DETECT_HEIGHT, fps=60, to_ide=True)
    MediaManager.init()
    sensor.run()

def camera_deinit():
    global sensor
    if sensor: sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
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
    while True:
        fps.tick()
        try:
            os.exitpoint()
            global sensor
            # 1. 抓取彩色原图
            img = sensor.snapshot()
            
            # 2. 生成用于算法识别的黑白副本
            # copy() 是为了不破坏原图(彩色用于显示)，to_grayscale 转灰度，binary 二值化
            img_algo = img.copy().to_grayscale()
            img_algo.binary([target_threshold])
            
            # 3. 在黑白副本上进行矩形识别
            found = False
            for r in img_algo.find_rects(threshold = 10000):
                corners = r.corners()
                t_cx, t_cy = get_target_center(corners)
                dx = t_cx - IMG_CENTER_X
                dy = t_cy - IMG_CENTER_Y
                
                # --- 4. 将识别结果绘制在【彩色原图】上 ---
                img.draw_rectangle([v for v in r.rect()], color = (255, 0, 0), thickness=2)
                img.draw_cross(t_cx, t_cy, color=(0, 0, 255), size=15) # 蓝色目标中心
                img.draw_cross(IMG_CENTER_X, IMG_CENTER_Y, color=(255, 255, 0), size=10) # 黄色参考中心
                img.draw_line(IMG_CENTER_X, IMG_CENTER_Y, t_cx, t_cy, color=(255, 255, 255))
                img.draw_string(t_cx + 10, t_cy + 10, "dx:%d dy:%d" % (dx, dy), color=(255, 255, 255), scale=2)
                
                print(f"Target Found -> dx: {dx}, dy: {dy}")
                found = True

            # 5. 显示彩色预览图
            Display.show_image(img)

            # 6. 显式释放所有图像资源，防止 OOM 或 snapshot 失败
            del img_algo
            del img
            gc.collect()
            
            # 实时打印 FPS
            print(f"FPS: {fps.fps():.2f}")
            
        except KeyboardInterrupt: break
        except BaseException as e:
            sys.print_exception(e)
            break

def main():
    os.exitpoint(os.EXITPOINT_ENABLE)
    camera_is_init = False
    try:
        print("--- rect_02 启动 (彩色预览模式) ---")
        camera_init()
        camera_is_init = True
        capture_picture()
    except Exception as e:
        sys.print_exception(e)
    finally:
        if camera_is_init:
            camera_deinit()

if __name__ == "__main__":
    main()

# Find Rects Wire-Stability Test
#
# Based on examples/11-Feature-Detection/find_rects.py.
# This version is tuned for testing camera extension-wire stability:
# - use Sensor(id=2) and a 1280x720 base mode like newer CV/AI examples
# - grayscale input by default to reduce per-frame data pressure
# - LCD output instead of IDE virtual display
# - fullscreen LCD feedback by default, with grayscale frames converted to RGB565 for display
# - optional switches to enable find_rects() step by step
import time, os, gc, sys
import image

from media.sensor import *
from media.display import *
from media.media import *

SENSOR_BASE_WIDTH = 1280
SENSOR_BASE_HEIGHT = 720
DETECT_WIDTH = ALIGN_UP(640, 16)
DETECT_HEIGHT = 480

LCD_WIDTH = 800
LCD_HEIGHT = 480
LCD_X_SCALE = LCD_WIDTH / DETECT_WIDTH
LCD_Y_SCALE = LCD_HEIGHT / DETECT_HEIGHT

SENSOR_ID = 2
SENSOR_FPS = 90
DISPLAY_FPS = 15
USE_GRAYSCALE = True
FULLSCREEN_SCALE = True
ENABLE_FIND_RECTS = True
RECT_THRESHOLD = 10000
FORCE_RGB565_LCD_FEEDBACK = True

sensor = None

def camera_init():
    global sensor

    sensor = Sensor(id=SENSOR_ID, width=SENSOR_BASE_WIDTH, height=SENSOR_BASE_HEIGHT, fps=SENSOR_FPS)
    sensor.reset()

    # If the extension wire is marginal, also try toggling these two settings.
    # sensor.set_hmirror(False)
    # sensor.set_vflip(False)

    sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    sensor.set_pixformat(Sensor.GRAYSCALE if USE_GRAYSCALE else Sensor.RGB565)

    Display.init(Display.ST7701, width=LCD_WIDTH, height=LCD_HEIGHT, fps=DISPLAY_FPS, to_ide=False)
    MediaManager.init()
    sensor.run()

def camera_deinit():
    global sensor
    if sensor:
        sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    MediaManager.deinit()

def capture_picture():
    fps = time.clock()
    display_img = image.Image(LCD_WIDTH, LCD_HEIGHT, image.RGB565)
    frame_count = 0

    while True:
        fps.tick()
        try:
            os.exitpoint()
            global sensor
            img = sensor.snapshot()
            frame_count += 1

            if ENABLE_FIND_RECTS:
                for r in img.find_rects(threshold=RECT_THRESHOLD):
                    rect_color = 255 if USE_GRAYSCALE else (255, 0, 0)
                    corner_color = 255 if USE_GRAYSCALE else (0, 255, 0)
                    img.draw_rectangle([v for v in r.rect()], color=rect_color)
                    for p in r.corners():
                        img.draw_circle(p[0], p[1], 5, color=corner_color)
                    print(r)
            else:
                text_color = 255 if USE_GRAYSCALE else (255, 255, 0)
                img.draw_string(10, 10, "wire test %d" % frame_count, color=text_color, scale=2)

            display_src = img
            if FORCE_RGB565_LCD_FEEDBACK and USE_GRAYSCALE:
                display_src = img.to_rgb565()

            if FULLSCREEN_SCALE:
                display_img.clear()
                display_img.draw_image(display_src, 0, 0, x_scale=LCD_X_SCALE, y_scale=LCD_Y_SCALE)
                Display.show_image(display_img)
            else:
                Display.show_image(display_src)

            if display_src is not img:
                display_src = None
            img = None
            gc.collect()
            print("FPS:", fps.fps())
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
        print("test_rect_wire camera init")
        camera_init()
        camera_is_init = True
        print("test_rect_wire capture start")
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

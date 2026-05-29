# Find Rects LCD Example
#
# Based on examples/11-Feature-Detection/find_rects.py.
# The camera and rectangle detection keep the original 320x240 RGB565 frame,
# while the preview is scaled to fill the 800x480 ST7701 LCD.
import time, os, gc, sys
import image

from media.sensor import *
from media.display import *
from media.media import *

DETECT_WIDTH = ALIGN_UP(320, 16)
DETECT_HEIGHT = 240
LCD_WIDTH = 800
LCD_HEIGHT = 480
LCD_X_SCALE = LCD_WIDTH / DETECT_WIDTH
LCD_Y_SCALE = LCD_HEIGHT / DETECT_HEIGHT

sensor = None

def camera_init():
    global sensor

    # construct a Sensor object with default configure
    sensor = Sensor(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    # sensor reset
    sensor.reset()
    # set hmirror
    # sensor.set_hmirror(False)
    # sensor vflip
    # sensor.set_vflip(False)

    # set chn0 output size
    sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    # set chn0 output format
    sensor.set_pixformat(Sensor.RGB565)

    # use LCD as display output
    Display.init(Display.ST7701, width=LCD_WIDTH, height=LCD_HEIGHT, fps=100, to_ide=False)
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

def capture_picture():
    fps = time.clock()
    display_img = image.Image(LCD_WIDTH, LCD_HEIGHT, image.RGB565)

    while True:
        fps.tick()
        try:
            os.exitpoint()
            global sensor
            img = sensor.snapshot()

            # `threshold` below should be set to a high enough value to filter out noise
            # rectangles detected in the image which have low edge magnitudes. Rectangles
            # have larger edge magnitudes the larger and more contrasty they are...

            for r in img.find_rects(threshold=10000):
                img.draw_rectangle([v for v in r.rect()], color=(255, 0, 0))
                for p in r.corners():
                    img.draw_circle(p[0], p[1], 5, color=(0, 255, 0))
                print(r)

            # draw result to LCD fullscreen
            display_img.clear()
            display_img.draw_image(img, 0, 0, x_scale=LCD_X_SCALE, y_scale=LCD_Y_SCALE)
            Display.show_image(display_img)
            img = None

            gc.collect()
            print(fps.fps())
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

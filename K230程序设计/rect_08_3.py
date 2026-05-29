# ------------------------------------------------------------------------
# rect_08_3.py
# 基于 rect_08.py 的 MemoryError 退避恢复版本：
# 1. 保留 LAB 阈值、形态学滤波、动态 ROI、GPIO2 输出和候选调试能力。
# 2. MemoryError 后不再立刻全屏重试，而是跳过若干帧 find_rects，让 fast frame buffer stack 恢复。
# 3. 恢复期临时提高 find_rects 阈值并优先围绕上次目标 ROI 搜索，连续溢出时逐步增加跳帧数。
# ------------------------------------------------------------------------
import time, os, gc, sys, math

from media.sensor import *
from media.display import *
from media.media import *
from machine import Pin
from machine import FPIOA

H_FOV_DEG = 60.0
V_FOV_DEG = 35.0

H_TAN_HALF_FOV = math.tan(math.radians(H_FOV_DEG / 2.0))
V_TAN_HALF_FOV = math.tan(math.radians(V_FOV_DEG / 2.0))

DETECT_WIDTH = ALIGN_UP(320, 16)
DETECT_HEIGHT = 240

IMG_CENTER_X = DETECT_WIDTH // 2
IMG_CENTER_Y = DETECT_HEIGHT // 2

LAB_TARGET_THRESHOLD = (0, 24, -18, 15, -17, 22)
LAB_BINARY_INVERT = True
DEBUG_CANDIDATES = False
DRAW_TEXT_OVERLAY = False

STATE_SEARCHING = 0
STATE_LOCKED = 1
STATE_COASTING = 2

MIN_ASPECT_RATIO = 1.1
MAX_ASPECT_RATIO = 1.8
MIN_AREA = 3000
MAX_AREA = 35000
MIN_DENSITY_MEAN = 70
BORDER_REJECT_MARGIN = 2

ROI_MARGIN = 35
MAX_COASTING_FRAMES = 3
ROI_EXPAND_MARGIN = 45
MAX_ROI_EXPAND_STEPS = 2
ROI_FIND_RECTS_THRESHOLD = 8000
FULLSCREEN_FIND_RECTS_THRESHOLD = 16000
FULLSCREEN_SEARCH_INTERVAL = 3

RECOVERY_BASE_SKIP_FRAMES = 10
RECOVERY_MAX_SKIP_FRAMES = 60
RECOVERY_FIND_RECTS_THRESHOLD = 32000
RECOVERY_SEARCH_INTERVAL = 8
RECOVERY_LAST_RECT_MARGIN = 40
RESET_CAMERA_ON_MEMORY_ERROR = False

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
    sensor = Sensor(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    sensor.reset()

    sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    sensor.set_pixformat(Sensor.RGB565)

    Display.init(Display.VIRT, width=DETECT_WIDTH, height=DETECT_HEIGHT, fps=100, to_ide=True)
    MediaManager.init()
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

def camera_soft_reset():
    global sensor
    try:
        if sensor:
            sensor.stop()
    except Exception:
        pass
    try:
        Display.deinit()
    except Exception:
        pass
    try:
        MediaManager.deinit()
    except Exception:
        pass
    gc.collect()
    time.sleep_ms(200)
    camera_init()

def get_target_center(corners):
    x1, y1 = corners[0]; x2, y2 = corners[2]
    x3, y3 = corners[1]; x4, y4 = corners[3]
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 0.0001:
        return (x1 + x2 + x3 + x4) // 4, (y1 + y2 + y3 + y4) // 4
    ix = ((x1*y2 - y1*x2)*(x3 - x4) - (x1 - x2)*(x3*y4 - y3*x4)) // denom
    iy = ((x1*y2 - y1*x2)*(y3 - y4) - (y1 - y2)*(x3*y4 - y3*x4)) // denom
    return int(ix), int(iy)

def validate_target_candidate(img, r):
    x, y, w, h = r.rect()
    if (x <= BORDER_REJECT_MARGIN or y <= BORDER_REJECT_MARGIN or
            x + w >= DETECT_WIDTH - BORDER_REJECT_MARGIN or
            y + h >= DETECT_HEIGHT - BORDER_REJECT_MARGIN):
        return False

    w, h = r.w(), r.h()
    area = w * h
    aspect_ratio = float(w) / h if h != 0 else 0

    if not (MIN_ASPECT_RATIO <= aspect_ratio <= MAX_ASPECT_RATIO):
        return False
    if not (MIN_AREA <= area <= MAX_AREA):
        return False

    stat = img.statistics(roi=r.rect())
    if stat.mean() < MIN_DENSITY_MEAN:
        return False

    return True

def get_candidate_reject_reason(img, r):
    x, y, w, h = r.rect()
    if (x <= BORDER_REJECT_MARGIN or y <= BORDER_REJECT_MARGIN or
            x + w >= DETECT_WIDTH - BORDER_REJECT_MARGIN or
            y + h >= DETECT_HEIGHT - BORDER_REJECT_MARGIN):
        area = w * h
        aspect_ratio = float(w) / h if h != 0 else 0
        stat = img.statistics(roi=r.rect())
        return "border", area, aspect_ratio, stat.mean()

    w, h = r.w(), r.h()
    area = w * h
    aspect_ratio = float(w) / h if h != 0 else 0
    stat = img.statistics(roi=r.rect())
    mean = stat.mean()

    if not (MIN_ASPECT_RATIO <= aspect_ratio <= MAX_ASPECT_RATIO):
        return "aspect", area, aspect_ratio, mean
    if not (MIN_AREA <= area <= MAX_AREA):
        return "area", area, aspect_ratio, mean
    if mean < MIN_DENSITY_MEAN:
        return "mean", area, aspect_ratio, mean
    return "ok", area, aspect_ratio, mean

def clamp_roi(x, y, w, h):
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(DETECT_WIDTH, x + w)
    y2 = min(DETECT_HEIGHT, y + h)
    return [x1, y1, x2 - x1, y2 - y1]

def calculate_search_roi(r):
    rx, ry, rw, rh = r.rect()
    return clamp_roi(rx - ROI_MARGIN, ry - ROI_MARGIN, rw + 2 * ROI_MARGIN, rh + 2 * ROI_MARGIN)

def calculate_recovery_roi_from_rect(rect):
    rx, ry, rw, rh = rect
    return clamp_roi(
        rx - RECOVERY_LAST_RECT_MARGIN,
        ry - RECOVERY_LAST_RECT_MARGIN,
        rw + 2 * RECOVERY_LAST_RECT_MARGIN,
        rh + 2 * RECOVERY_LAST_RECT_MARGIN,
    )

def expand_search_roi(roi, margin):
    rx, ry, rw, rh = roi
    return clamp_roi(rx - margin, ry - margin, rw + 2 * margin, rh + 2 * margin)

def is_fullscreen_roi(roi):
    return roi[0] == 0 and roi[1] == 0 and roi[2] >= DETECT_WIDTH and roi[3] >= DETECT_HEIGHT

def capture_picture():
    frame_times = []
    fps_val = 0.0

    tracking_state = STATE_SEARCHING
    coast_counter = 0
    search_roi = [0, 0, DETECT_WIDTH, DETECT_HEIGHT]

    last_rect = None
    last_cx = 0
    last_cy = 0
    last_dx = 0
    last_dy = 0
    last_yaw = 0.0
    last_pitch = 0.0
    roi_expand_steps = 0
    fullscreen_search_counter = 0

    recovery_skip_frames = 0
    memory_error_count = 0
    recovery_search_counter = 0

    while True:
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
            img = sensor.snapshot()

            in_recovery = recovery_skip_frames > 0
            active_fullscreen = is_fullscreen_roi(search_roi)
            run_rect_search = True

            if in_recovery:
                recovery_skip_frames -= 1
                run_rect_search = False
            elif memory_error_count > 0:
                # After a stack overflow, avoid repeatedly probing the same problematic ROI.
                # Fall back to a sparse, high-threshold fullscreen search.
                active_fullscreen = True
                search_roi = [0, 0, DETECT_WIDTH, DETECT_HEIGHT]
                recovery_search_counter += 1
                run_rect_search = (recovery_search_counter % RECOVERY_SEARCH_INTERVAL) == 1
            elif tracking_state == STATE_SEARCHING and active_fullscreen:
                fullscreen_search_counter += 1
                run_rect_search = (fullscreen_search_counter % FULLSCREEN_SEARCH_INTERVAL) == 1
            else:
                fullscreen_search_counter = 0

            img.binary([LAB_TARGET_THRESHOLD], invert=LAB_BINARY_INVERT, roi=search_roi)

            if run_rect_search and not active_fullscreen and memory_error_count == 0:
                img.dilate(1, roi=search_roi)
                img.erode(1, roi=search_roi)

            rects = None
            if run_rect_search:
                if memory_error_count > 0:
                    rect_threshold = RECOVERY_FIND_RECTS_THRESHOLD
                else:
                    rect_threshold = FULLSCREEN_FIND_RECTS_THRESHOLD if active_fullscreen else ROI_FIND_RECTS_THRESHOLD
                rects = img.find_rects(threshold=rect_threshold, roi=search_roi)

            best_rect = None

            if rects:
                for r in rects:
                    if DEBUG_CANDIDATES and memory_error_count == 0:
                        reason, area, aspect_ratio, mean = get_candidate_reject_reason(img, r)
                        img.draw_rectangle([v for v in r.rect()], color=255, thickness=1)
                        print(f"Rect cand -> reason:{reason} rect:{r.rect()} area:{area} aspect:{aspect_ratio:.2f} mean:{mean:.1f}")
                        if reason == "ok":
                            if best_rect is None or area > (best_rect.w() * best_rect.h()):
                                best_rect = r
                    elif validate_target_candidate(img, r):
                        if best_rect is None or (r.w() * r.h()) > (best_rect.w() * best_rect.h()):
                            best_rect = r

            if best_rect is not None:
                set_gpio2_high(True)
                tracking_state = STATE_LOCKED
                coast_counter = 0
                roi_expand_steps = 0
                memory_error_count = 0
                recovery_skip_frames = 0
                recovery_search_counter = 0

                search_roi = calculate_search_roi(best_rect)

                corners = best_rect.corners()
                t_cx, t_cy = get_target_center(corners)

                dx = t_cx - IMG_CENTER_X
                dy = t_cy - IMG_CENTER_Y

                angle_x_rad = math.atan((dx / (DETECT_WIDTH / 2.0)) * H_TAN_HALF_FOV)
                angle_y_rad = math.atan((dy / (DETECT_HEIGHT / 2.0)) * V_TAN_HALF_FOV)

                yaw_angle = math.degrees(angle_x_rad)
                pitch_angle = math.degrees(angle_y_rad)

                img.draw_rectangle([v for v in best_rect.rect()], color=255, thickness=2)
                img.draw_cross(t_cx, t_cy, color=255, size=15)
                img.draw_rectangle(search_roi, color=255, thickness=1)

                img.draw_cross(IMG_CENTER_X, IMG_CENTER_Y, color=255, size=10)
                img.draw_line(IMG_CENTER_X, IMG_CENTER_Y, t_cx, t_cy, color=255)
                if DRAW_TEXT_OVERLAY:
                    img.draw_string(t_cx + 10, t_cy + 10, "dx:%d dy:%d" % (dx, dy), color=255, scale=2)
                    img.draw_string(t_cx + 10, t_cy + 30, "Yaw:%.1f Pitch:%.1f" % (yaw_angle, pitch_angle), color=255, scale=2)

                last_rect = [v for v in best_rect.rect()]
                last_cx, last_cy = t_cx, t_cy
                last_dx, last_dy = dx, dy
                last_yaw, last_pitch = yaw_angle, pitch_angle

                print(f"Target LOCKED (LAB Recovery ROI) -> dx: {dx:3d}, dy: {dy:3d} | Yaw: {yaw_angle:5.1f}°, Pitch: {pitch_angle:5.1f}° | ROI: {search_roi} | FPS: {fps_val:.1f}")

            else:
                set_gpio2_high(False)
                if tracking_state == STATE_LOCKED:
                    tracking_state = STATE_COASTING
                    coast_counter = MAX_COASTING_FRAMES
                elif tracking_state == STATE_COASTING:
                    coast_counter -= 1
                    if coast_counter <= 0:
                        if (not active_fullscreen) and roi_expand_steps < MAX_ROI_EXPAND_STEPS:
                            roi_expand_steps += 1
                            search_roi = expand_search_roi(search_roi, ROI_EXPAND_MARGIN)
                            coast_counter = MAX_COASTING_FRAMES
                            print(f"Target Reacquire Expand ROI [{roi_expand_steps}] -> ROI: {search_roi} | FPS: {fps_val:.1f}")
                        else:
                            tracking_state = STATE_SEARCHING
                            roi_expand_steps = 0
                            search_roi = [0, 0, DETECT_WIDTH, DETECT_HEIGHT]

                if tracking_state == STATE_COASTING and last_rect is not None:
                    img.draw_rectangle(last_rect, color=255, thickness=2)
                    img.draw_cross(last_cx, last_cy, color=255, size=15)
                    img.draw_rectangle(search_roi, color=255, thickness=1)

                    img.draw_cross(IMG_CENTER_X, IMG_CENTER_Y, color=255, size=10)
                    img.draw_line(IMG_CENTER_X, IMG_CENTER_Y, last_cx, last_cy, color=255)
                    if DRAW_TEXT_OVERLAY:
                        img.draw_string(last_cx + 10, last_cy + 10, "dx:%d dy:%d (Coast)" % (last_dx, last_dy), color=255, scale=2)
                        img.draw_string(last_cx + 10, last_cy + 30, "Yaw:%.1f Pitch:%.1f" % (last_yaw, last_pitch), color=255, scale=2)

                    print(f"Target Coasting [{coast_counter}] -> Keep ROI: {search_roi} | FPS: {fps_val:.1f}")
                else:
                    if in_recovery:
                        print(f"Recovery Skip... remain:{recovery_skip_frames} | FPS: {fps_val:.1f}")
                    elif run_rect_search:
                        if DRAW_TEXT_OVERLAY:
                            img.draw_string(10, 40, "Searching Fullscreen...", color=255, scale=2)
                        print(f"Target Searching Fullscreen... | FPS: {fps_val:.1f}")
                    else:
                        if DRAW_TEXT_OVERLAY:
                            img.draw_string(10, 40, "Searching Skip...", color=255, scale=2)
                        print(f"Target Searching Skip... | FPS: {fps_val:.1f}")

            if DRAW_TEXT_OVERLAY:
                img.draw_string(10, 10, "FPS: %.2f" % fps_val, color=255, scale=2)
            Display.show_image(img)

            rects = None
            best_rect = None
            img = None
            gc.collect()

        except KeyboardInterrupt as e:
            print("user stop")
            break
        except MemoryError as e:
            set_gpio2_high(False)
            memory_error_count += 1
            recovery_skip_frames = min(RECOVERY_BASE_SKIP_FRAMES * memory_error_count, RECOVERY_MAX_SKIP_FRAMES)
            tracking_state = STATE_SEARCHING
            coast_counter = 0
            roi_expand_steps = 0
            fullscreen_search_counter = 0
            recovery_search_counter = 0
            search_roi = [0, 0, DETECT_WIDTH, DETECT_HEIGHT]
            rects = None
            best_rect = None
            img = None
            gc.collect()
            if RESET_CAMERA_ON_MEMORY_ERROR:
                print(f"MemoryError: reset camera, backoff skip {recovery_skip_frames} frames")
                camera_soft_reset()
            else:
                print(f"MemoryError: backoff skip {recovery_skip_frames} frames")
            continue
        except BaseException as e:
            import sys
            sys.print_exception(e)
            break

def main():
    os.exitpoint(os.EXITPOINT_ENABLE)
    camera_is_init = False
    try:
        print("--- rect_08_3 启动 (LAB 阈值 MemoryError 退避恢复版) ---")
        camera_init()
        camera_is_init = True
        print("camera capture start with LAB recovery recognition")
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

# ------------------------------------------------------------------------
# rect_08_1.py
# rect_08 的 LAB 阈值彩色预览版本：
# 1. 复用 rect_08 的 LAB 反相二值化、动态 ROI、GPIO2 输出和 MemoryError 恢复策略。
# 2. 算法在 RGB565 副本上执行，识别结果绘制回彩色原图显示。
# 3. 需要与 rect_08.py 放在同一目录下运行。
# ------------------------------------------------------------------------
import gc
import os
import sys
import time

import rect_08 as base

def capture_picture():
    frame_times = []
    fps_val = 0.0

    tracking_state = base.STATE_SEARCHING
    coast_counter = 0
    search_roi = [0, 0, base.DETECT_WIDTH, base.DETECT_HEIGHT]

    last_rect = None
    last_cx = 0
    last_cy = 0
    last_dx = 0
    last_dy = 0
    last_yaw = 0.0
    last_pitch = 0.0
    roi_expand_steps = 0
    fullscreen_search_counter = 0

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
            img = base.sensor.snapshot()
            img_algo = img.copy()

            active_fullscreen = base.is_fullscreen_roi(search_roi)
            run_rect_search = True
            if tracking_state == base.STATE_SEARCHING and active_fullscreen:
                fullscreen_search_counter += 1
                run_rect_search = (fullscreen_search_counter % base.FULLSCREEN_SEARCH_INTERVAL) == 1
            else:
                fullscreen_search_counter = 0

            img_algo.binary([base.LAB_TARGET_THRESHOLD], invert=base.LAB_BINARY_INVERT, roi=search_roi)

            if run_rect_search and not active_fullscreen:
                img_algo.dilate(1, roi=search_roi)
                img_algo.erode(1, roi=search_roi)

            rects = None
            if run_rect_search:
                rect_threshold = base.FULLSCREEN_FIND_RECTS_THRESHOLD if active_fullscreen else base.ROI_FIND_RECTS_THRESHOLD
                rects = img_algo.find_rects(threshold=rect_threshold, roi=search_roi)

            best_rect = None

            if rects:
                for r in rects:
                    if base.validate_target_candidate(img_algo, r):
                        if best_rect is None or (r.w() * r.h()) > (best_rect.w() * best_rect.h()):
                            best_rect = r

            if best_rect is not None:
                base.set_gpio2_high(True)
                tracking_state = base.STATE_LOCKED
                coast_counter = 0
                roi_expand_steps = 0

                search_roi = base.calculate_search_roi(best_rect)

                corners = best_rect.corners()
                t_cx, t_cy = base.get_target_center(corners)

                dx = t_cx - base.IMG_CENTER_X
                dy = t_cy - base.IMG_CENTER_Y

                angle_x_rad = base.math.atan((dx / (base.DETECT_WIDTH / 2.0)) * base.H_TAN_HALF_FOV)
                angle_y_rad = base.math.atan((dy / (base.DETECT_HEIGHT / 2.0)) * base.V_TAN_HALF_FOV)

                yaw_angle = base.math.degrees(angle_x_rad)
                pitch_angle = base.math.degrees(angle_y_rad)

                img.draw_rectangle([v for v in best_rect.rect()], color=(255, 0, 0), thickness=2)
                img.draw_cross(t_cx, t_cy, color=(0, 0, 255), size=15)
                img.draw_rectangle(search_roi, color=(0, 255, 0), thickness=1)

                img.draw_cross(base.IMG_CENTER_X, base.IMG_CENTER_Y, color=(255, 255, 0), size=10)
                img.draw_line(base.IMG_CENTER_X, base.IMG_CENTER_Y, t_cx, t_cy, color=(255, 255, 255))
                img.draw_string(t_cx + 10, t_cy + 10, "dx:%d dy:%d" % (dx, dy), color=(255, 255, 255), scale=2)
                img.draw_string(t_cx + 10, t_cy + 30, "Yaw:%.1f Pitch:%.1f" % (yaw_angle, pitch_angle), color=(255, 255, 0), scale=2)

                last_rect = [v for v in best_rect.rect()]
                last_cx, last_cy = t_cx, t_cy
                last_dx, last_dy = dx, dy
                last_yaw, last_pitch = yaw_angle, pitch_angle

                print(f"Target LOCKED (LAB Color ROI) -> dx: {dx:3d}, dy: {dy:3d} | Yaw: {yaw_angle:5.1f}°, Pitch: {pitch_angle:5.1f}° | ROI: {search_roi} | FPS: {fps_val:.1f}")

            else:
                base.set_gpio2_high(False)
                if tracking_state == base.STATE_LOCKED:
                    tracking_state = base.STATE_COASTING
                    coast_counter = base.MAX_COASTING_FRAMES
                elif tracking_state == base.STATE_COASTING:
                    coast_counter -= 1
                    if coast_counter <= 0:
                        if (not active_fullscreen) and roi_expand_steps < base.MAX_ROI_EXPAND_STEPS:
                            roi_expand_steps += 1
                            search_roi = base.expand_search_roi(search_roi, base.ROI_EXPAND_MARGIN)
                            coast_counter = base.MAX_COASTING_FRAMES
                            print(f"Target Reacquire Expand ROI [{roi_expand_steps}] -> ROI: {search_roi} | FPS: {fps_val:.1f}")
                        else:
                            tracking_state = base.STATE_SEARCHING
                            roi_expand_steps = 0
                            search_roi = [0, 0, base.DETECT_WIDTH, base.DETECT_HEIGHT]

                if tracking_state == base.STATE_COASTING:
                    img.draw_rectangle(last_rect, color=(255, 0, 0), thickness=2)
                    img.draw_cross(last_cx, last_cy, color=(0, 0, 255), size=15)
                    img.draw_rectangle(search_roi, color=(0, 255, 0), thickness=1)

                    img.draw_cross(base.IMG_CENTER_X, base.IMG_CENTER_Y, color=(255, 255, 0), size=10)
                    img.draw_line(base.IMG_CENTER_X, base.IMG_CENTER_Y, last_cx, last_cy, color=(255, 255, 255))
                    img.draw_string(last_cx + 10, last_cy + 10, "dx:%d dy:%d (Coast)" % (last_dx, last_dy), color=(255, 255, 255), scale=2)
                    img.draw_string(last_cx + 10, last_cy + 30, "Yaw:%.1f Pitch:%.1f" % (last_yaw, last_pitch), color=(255, 255, 0), scale=2)

                    print(f"Target Coasting [{coast_counter}] -> Keep ROI: {search_roi} | FPS: {fps_val:.1f}")
                else:
                    if run_rect_search:
                        img.draw_string(10, 40, "Searching Fullscreen...", color=(255, 255, 0), scale=2)
                        print(f"Target Searching Fullscreen... | FPS: {fps_val:.1f}")
                    else:
                        img.draw_string(10, 40, "Searching Skip...", color=(255, 255, 0), scale=2)
                        print(f"Target Searching Skip... | FPS: {fps_val:.1f}")

            img.draw_string(10, 10, "FPS: %.2f" % fps_val, color=(255, 255, 0), scale=2)

            base.Display.show_image(img)

            rects = None
            best_rect = None
            del img_algo
            img = None
            gc.collect()

        except KeyboardInterrupt:
            print("user stop")
            break
        except MemoryError:
            base.set_gpio2_high(False)
            tracking_state = base.STATE_SEARCHING
            coast_counter = 0
            roi_expand_steps = 0
            fullscreen_search_counter = 0
            search_roi = [0, 0, base.DETECT_WIDTH, base.DETECT_HEIGHT]
            last_rect = None
            last_cx = 0
            last_cy = 0
            last_dx = 0
            last_dy = 0
            last_yaw = 0.0
            last_pitch = 0.0
            rects = None
            best_rect = None
            img_algo = None
            img = None
            gc.collect()
            print("MemoryError: reset to throttled fullscreen LAB color search and continue")
            continue
        except BaseException as e:
            sys.print_exception(e)
            break

def main():
    os.exitpoint(os.EXITPOINT_ENABLE)
    camera_is_init = False
    try:
        print("--- rect_08_1 启动 (LAB 阈值彩色预览版) ---")
        base.camera_init()
        camera_is_init = True
        print("camera capture start with LAB color preview recognition")
        capture_picture()
    except Exception as e:
        sys.print_exception(e)
    finally:
        if camera_is_init:
            print("camera deinit")
            base.camera_deinit()

if __name__ == "__main__":
    main()

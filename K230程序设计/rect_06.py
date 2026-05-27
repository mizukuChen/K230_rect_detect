# ------------------------------------------------------------------------
# rect_06.py
# 基于 rect_05.py (时空差分防抖版) 的多重靶标特征校验版 (方案六)：
# 1. 引入几何长宽比与面积过滤：限制宽高比在 1.1~1.8 之间，限制面积在 3000~35000 像素之间。
# 2. 引入内部二值化像素占比验证：对候选框进行 C 层的 statistics() 统计，白色像素占比平均值需达 170 以上。
# 3. 引入时序多帧稳定确认：在搜寻状态下，靶标必须连续 3 帧在相近位置稳定出现，才正式建立锁定。
# 4. 保留帧间差分标准差 (Stdev) 跳过冗余计算的优化，保证极致的 FPS 速度与零抖动。
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
STDEV_THRESHOLD = 3.5

# --- 空间门限与状态机防突变配置 (方案一) ---
MAX_DISPLACEMENT = 60      # 两帧之间允许的最大像素位移，超过则认为是背景噪点
MAX_COASTING_FRAMES = 3    # 目标短暂丢失时的最大容忍/维持帧数

STATE_SEARCHING = 0
STATE_LOCKED = 1
STATE_COASTING = 2

# --- 靶标验证过滤参数 (方案六新增) ---
MIN_ASPECT_RATIO = 1.1      # A4靶标最小长宽比 (标准 A4 约为 1.41)
MAX_ASPECT_RATIO = 1.8      # A4靶标最大长宽比 (考虑透视形变)
MIN_AREA = 3000             # A4靶标在 320x240 分辨率下的最小面积（像素）
MAX_AREA = 35000            # A4靶标在 320x240 分辨率下的最大面积（像素）
MIN_DENSITY_MEAN = 170      # 靶标内部二值化后白色像素平均亮度阈值 (0-255，值越高说明内部白纸比例越大)
STABLE_CONFIRM_FRAMES = 3   # 搜寻状态下需要连续多少帧检测到稳定靶标才锁定
MAX_STABLE_DISPLACEMENT = 15 # 搜寻时两帧之间允许的最大漂移距离，超过则重置计数

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

# ------------------------------------------------------------------------
# 核心过滤验证函数：校验单个矩形是否符合靶标物理特征 (几何 + 占比过滤)
# ------------------------------------------------------------------------
def validate_target_candidate(img, r):
    w, h = r.w(), r.h()
    area = w * h
    aspect_ratio = float(w) / h if h != 0 else 0

    # 1. 几何过滤 (长宽比与面积大小)
    if not (MIN_ASPECT_RATIO <= aspect_ratio <= MAX_ASPECT_RATIO):
        return False
    if not (MIN_AREA <= area <= MAX_AREA):
        return False

    # 2. 内部二值化像素占比验证 (只针对通过了几何初筛的候选框调用，降低开销)
    stat = img.statistics(roi=r.rect())
    if stat.mean() < MIN_DENSITY_MEAN:
        return False

    return True

def capture_picture():
    # --- 瞬时帧率计算变量 (滑动窗口，以1秒为区间统计真实帧率) ---
    frame_times = []
    fps_val = 0.0
    
    # --- 初始化时空缓存与状态机变量 ---
    prev_img = None           # 保存上一帧的原始灰度拷贝
    tracking_state = STATE_SEARCHING
    coast_counter = 0
    
    last_rect = None          # 上一次检测到的矩形框坐标 [x, y, w, h]
    last_cx = 0               # 上一次的目标中心 x
    last_cy = 0               # 上一次的目标中心 y
    last_dx = 0               # 上一次的中心偏差 dx
    last_dy = 0               # 上一次的中心偏差 dy
    last_yaw = 0.0            # 上一次解算出的 Yaw 偏角
    last_pitch = 0.0          # 上一次解算出的 Pitch 偏角

    # --- 搜寻期稳定计数器 ---
    stable_counter = 0        # 连续稳定帧数
    last_search_cx = 0        # 前一帧候选中心 x
    last_search_cy = 0        # 前一帧候选中心 y

    while True:
        # 计算滑动窗口瞬时帧率
        now_time = time.ticks_ms()
        frame_times.append(now_time)
        # 移出 1 秒 (1000 毫秒) 之前的帧时间戳
        while frame_times and time.ticks_diff(now_time, frame_times[0]) > 1000:
            frame_times.pop(0)
        
        # 计算最近 1 秒内的 FPS
        if len(frame_times) > 1:
            fps_val = (len(frame_times) - 1) * 1000.0 / time.ticks_diff(now_time, frame_times[0])
        else:
            fps_val = 0.0

        try:
            os.exitpoint()
            global sensor
            # 1. 抓取图像 (原始灰度图)
            img = sensor.snapshot()

            # 备份当前帧作为下一次的对比图（必须在二值化等破坏性原位操作之前复制）
            prev_img_temp = img.copy()

            skip_algo = False
            stdev = 0.0

            # 2. 时空差分评估：计算与上一帧的差分标准差
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

                print(f"Target Found (Cached) -> dx: {last_dx:3d}, dy: {last_dy:3d} | Yaw: {last_yaw:5.1f}°, Pitch: {last_pitch:5.1f}° | Stdev: {stdev:.2f} | FPS: {fps_val:.1f}")

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
                        # --- 搜寻模式：过滤并验证候选靶标 ---
                        valid_candidates = []
                        for r in rects:
                            if validate_target_candidate(img, r):
                                valid_candidates.append(r)
                        
                        if valid_candidates:
                            # 找出通过验证的所有候选矩形中面积最大的一只
                            candidate_rect = max(valid_candidates, key=lambda r: r.w() * r.h())
                            cx, cy = get_target_center(candidate_rect.corners())
                            
                            # 验证时序稳定性 (看和前一帧候选中心的漂移距离)
                            dist = math.sqrt((cx - last_search_cx)**2 + (cy - last_search_cy)**2)
                            if dist <= MAX_STABLE_DISPLACEMENT:
                                stable_counter += 1
                            else:
                                stable_counter = 1 # 发生大漂移，重新开始计数
                            
                            last_search_cx, last_search_cy = cx, cy
                            
                            # 只有连续稳定 3 帧才算真正确认并建立锁定
                            if stable_counter >= STABLE_CONFIRM_FRAMES:
                                best_rect = candidate_rect
                        else:
                            stable_counter = 0 # 没有找到任何满足特征的靶标，重置计数

                    else:
                        # --- 锁定/维持模式：寻找位置在 MAX_DISPLACEMENT 以内且特征合理的最近矩形 ---
                        min_dist = 99999
                        for r in rects:
                            corners = r.corners()
                            cx, cy = get_target_center(corners)
                            dist = math.sqrt((cx - last_cx)**2 + (cy - last_cy)**2)
                            if dist <= MAX_DISPLACEMENT and dist < min_dist:
                                # 在锁定态下同样进行几何与占比的双重校验，防止锁在漂移过来的背景上
                                if validate_target_candidate(img, r):
                                    min_dist = dist
                                    best_rect = r

                if best_rect is not None:
                    # --- 成功找到并确认目标 ---
                    tracking_state = STATE_LOCKED
                    coast_counter = 0
                    stable_counter = 0 # 已经锁定，重置搜寻期计数器

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

                    print(f"Target Locked -> dx: {dx:3d}, dy: {dy:3d} | Yaw: {yaw_angle:5.1f}°, Pitch: {pitch_angle:5.1f}° | Stdev: {stdev:.2f} | FPS: {fps_val:.1f}")
                else:
                    # --- 画面无目标或目标均在门限外 (未过校验/噪点突变) ---
                    if tracking_state == STATE_LOCKED:
                        tracking_state = STATE_COASTING
                        coast_counter = MAX_COASTING_FRAMES
                    elif tracking_state == STATE_COASTING:
                        coast_counter -= 1
                        if coast_counter <= 0:
                            tracking_state = STATE_SEARCHING
                            stable_counter = 0 # 彻底丢失，回到最初的搜寻计数
                    
                    if tracking_state == STATE_COASTING:
                        # 惯性滑行 (Coast) 状态：使用上一帧的缓存参数顶替
                        img.draw_rectangle(last_rect, color=255, thickness=2)
                        img.draw_cross(last_cx, last_cy, color=255, size=15)
                        img.draw_cross(IMG_CENTER_X, IMG_CENTER_Y, color=255, size=10)
                        img.draw_line(IMG_CENTER_X, IMG_CENTER_Y, last_cx, last_cy, color=255)

                        img.draw_string(last_cx + 10, last_cy + 10, "dx:%d dy:%d (Coast)" % (last_dx, last_dy), color=255, scale=2)
                        img.draw_string(last_cx + 10, last_cy + 30, "Yaw:%.1f Pitch:%.1f (Coast)" % (last_yaw, last_pitch), color=255, scale=2)
                        
                        print(f"Target Coasting [{coast_counter}] -> dx: {last_dx:3d}, dy: {last_dy:3d} | Stdev: {stdev:.2f} | FPS: {fps_val:.1f}")
                    else:
                        # 搜寻状态下显示正在搜寻中的稳定度进度
                        img.draw_string(10, 40, f"Searching... Stb:{stable_counter}/3", color=255, scale=2)
                        print(f"Target Searching... Stb:{stable_counter}/3 | Stdev: {stdev:.2f} | FPS: {fps_val:.1f}")

            # 4. 绘制 FPS 到屏幕
            img.draw_string(10, 10, "FPS: %.2f" % fps_val, color=255, scale=2)

            # 5. 显示到屏幕
            Display.show_image(img)

            # 6. 状态迭代与内存释放
            if prev_img is not None:
                del prev_img
            prev_img = prev_img_temp  # 转移最新的原始灰度拷贝

            del img
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
        print("--- rect_06 启动 (多重校验防抖版) ---")
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

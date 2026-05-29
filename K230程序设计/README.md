# K230 程序设计目录说明

本目录存放了 2025年电赛 E题——简易自行瞄准装置在 CanMV K230 平台上的视觉处理程序和方案文档。

> [!IMPORTANT]
> **重要规则：**
> 以后在此目录中**添加新文件**或**修改现有文件**时，**必须同步更新本 `README.md` 文件**中的对应介绍，以确保文档与代码库的实时一致性。

---

## 文件列表及功能说明

### 1. 核心目标识别与解算程序 (rect 系列)

*   **[rect_01.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect_01.py)** (低分辨率彩色预览版)
    *   **配置**：`320x240 RGB565` (彩色采集)
    *   **描述**：采用“RGB565单通道硬件采集 + 软件 `copy()` 转换为灰度与二值化后处理”的最稳妥架构。支持最大矩形识别、对角线交点中心点解算、视场角(FOV)物理偏转角解算，并在彩色画面上叠加绘制框线及调试信息，实时输出给 IDE 虚拟显示。
*   **[rect_02.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect_02.py)** (已废弃 - 硬件通道分流死锁版本)
    *   **描述**：尝试开启多个底层通道（如 `chn0` 和 `chn2` 等）以隔离预览流和算法流，希望在硬件层解决彩色预览与算法提取的并发冲突。然而由于 K230 硬件视频缓冲池 (VB Pool) 分配机制严苛且缓冲区不足，此架构运行即会导致内存死锁崩溃（报 `buffer_size 0` / `failed(3)`），仅作为负面典型和踩坑历史对比保留。
*   **[rect_03.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect_03.py)** (极速灰度识别版)
    *   **配置**：`320x240 GRAYSCALE` (纯灰度采集)
    *   **描述**：舍弃彩色画面以实现最高处理帧率。硬件层直接读取灰度图，在 Snapshot 缓冲区上直接二值化并执行矩形搜索与坐标偏差计算，降低 CPU 开销。
*   **[rect_04.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect_04.py)** (形态学滤波增强版 - 综合表现最佳)
    *   **配置**：`320x240 GRAYSCALE` (纯灰度采集)
    *   **描述**：在极速灰度版基础上引入形态学“闭运算”（先膨胀后腐蚀），能够自动缝合断裂的黑框边缘并去除边缘毛刺噪声，过滤出最大面积的目标矩形，大幅增强识别稳定性。**现已同步支持视场角(FOV)下的 Yaw / Pitch 物理偏转角度解算与叠加显示**。
*   **[rect_05.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect_05.py)** (时空差分防抖版)
    *   **配置**：`320x240 GRAYSCALE` (纯灰度采集)
    *   **描述**：基于 `rect_04.py` 的时空冗余优化版。引入帧间差分标准差 (Stdev) 指标，当图像几乎无变化且已锁定目标时，自动跳过形态学处理与矩形查找，复用历史计算结果。显著降低 CPU 消耗，稳定云台输出并防抖。
*   **[rect_06.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect_06.py)** (多重校验防抖版)
    *   **配置**：`320x240 GRAYSCALE` (纯灰度采集)
    *   **描述**：基于 `rect_05.py` 的多特征安全过滤版本。引入几何外轮廓校验（长宽比/面积限制）、内部像素密度均值校验以及时序多帧稳定滤波机制。彻底杜绝初始搜寻（SEARCHING）和锁定（LOCKED）状态下误识别背景杂乱物品为靶标的情况。**内置基于 1 秒滑动窗口（Sliding Window）的瞬时 FPS 估算器，每帧更新且无历史累积偏差**。
*   **[rect_07.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect_07.py)** (动态局部 ROI 追踪版)
    *   **配置**：`320x240 GRAYSCALE` (纯灰度采集)
    *   **描述**：基于 `rect_04.py` 的动态感兴趣区域（ROI）跟踪版本。转而通过动态缩放的局部搜索 ROI 来限制图像操作（二值化、形态学、矩形查找）。既实现了从物理层面上完全屏蔽 ROI 外的所有背景噪声，又极大地减少了每帧的像素处理数量，极大地提升了 FPS 处理速度（通常可达 40+ FPS）。同样支持短暂丢失时的滑行重获机制，**并同样配备 1 秒滑动窗口瞬时 FPS 估算器，反应极其灵敏**。当前版本参考 `examples/03-Machine/pin.py` / `pin_irq.py` 的 GPIO 初始化方式，将 Pin2 复用为 GPIO2，并在每帧识别到有效矩形时输出高电平，未识别到有效矩形时输出低电平。针对目标反复离屏/入屏导致的 fast frame buffer stack 压力，现改为“局部丢失先扩展 ROI，两次失败后才回全屏”，并对全屏 `find_rects()` 做降频和更高阈值处理；若仍触发 `MemoryError`，会重置到低频全屏搜索并继续运行，避免进程直接停止。
*   **[rect_07_1.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect_07_1.py)** (动态局部 ROI 彩色预览版)
    *   **配置**：`320x240 RGB565` (彩色采集)
    *   **描述**：参考 `rect_01.py` 的“彩色原图预览 + 灰度副本算法处理”架构，在 `rect_07.py` 的动态 ROI 追踪基础上改为 RGB565 彩色采集。每帧通过 `img.copy().to_grayscale()` 生成算法副本，在副本上执行 ROI 二值化、形态学滤波和矩形查找，再将靶标框、ROI 框、中心偏差、Yaw/Pitch 与 FPS 绘制回彩色原图显示。保留 GPIO2 有效目标输出：识别到有效矩形时置高电平，未识别到有效矩形时置低电平。
*   **[rect07_lcd.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect07_lcd.py)** (动态局部 ROI LCD 彩色输出版)
    *   **配置**：`320x240 RGB565` 摄像头采集，`800x480 ST7701` LCD 输出
    *   **描述**：基于 `rect_07_1.py` 的 LCD 显示版本，保留 RGB565 彩色采集、灰度副本识别、动态 ROI 追踪、GPIO2 有效目标输出以及彩色框线叠加逻辑；主要差异是显示后端由 IDE 虚拟显示 `Display.VIRT` 改为 LCD 屏 `Display.ST7701`，并关闭 `to_ide` 镜像输出。显示时复用一张 `800x480 RGB565` LCD 帧，通过 `draw_image(..., x_scale, y_scale)` 将 `320x240` 预览画面拉伸到整块 LCD。
*   **[rect_08.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect_08.py)** (LAB 阈值动态 ROI 追踪版)
    *   **配置**：`320x240 RGB565` (彩色采集)
    *   **描述**：基于当前 `rect_07.py` 的完整识别流程实现，动态 ROI、ROI 扩展重获、全屏搜索降频、GPIO2 输出、`MemoryError` 恢复、形态学、矩形查找与候选校验逻辑均保持一致；核心差异仅为 `rect_07.py` 使用灰度阈值，而本版本使用 `LAB_TARGET_THRESHOLD = (0, 24, -18, 15, -17, 22)` 配合 `invert=True` 做 LAB 反相二值化。由于 LAB/RGB 二值图的 `statistics().mean()` 实测低于灰度版，密度阈值调整为 `MIN_DENSITY_MEAN = 70`。本版本采集格式为 RGB565，最终输出黑白二值图。当前开启候选矩形调试输出，会打印每个 `find_rects` 候选的面积、长宽比、均值和过滤原因，便于排查“图像清楚但未锁定”的问题。
*   **[rect08_lcd.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect08_lcd.py)** (LAB 阈值动态 ROI LCD 全屏版)
    *   **配置**：`320x240 RGB565` 摄像头采集，`800x480 ST7701` LCD 输出
    *   **描述**：基于 `rect_08.py` 的 LCD 显示版本，保留 LAB 反相二值化、动态 ROI、ROI 扩展重获、全屏搜索降频、GPIO2 输出、`MemoryError` 恢复、形态学和候选校验逻辑；显示端改为 LCD，并复用一张 `800x480 RGB565` 显示帧，通过 `draw_image(..., x_scale, y_scale)` 将 `320x240` 黑白二值输出拉伸到 LCD 全屏。
*   **[rect09_lcd.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect09_lcd.py)** (Sensor id=2 + LAB 阈值动态 ROI LCD 版)
    *   **配置**：`Sensor(id=2, width=1280, height=720, fps=90)` 基础模式，输出 `320x240 RGB565`，`800x480 ST7701` LCD 输出
    *   **描述**：基于 `rect_08.py` 的 LAB 识别流程重构，保留 `LAB_TARGET_THRESHOLD = (0, 24, -18, 15, -17, 22)`、LAB 反相二值化、**全屏形态学滤波（闭运算）**、动态 ROI、ROI 扩展重获、**全屏每帧搜索（取消降频且门槛阈值降至 8000）**、GPIO2 输出 and `MemoryError` 恢复逻辑；采集路径改为当前连接线排查中使用的 `Sensor(id=2)` 新式初始化方式。为保证实时性，当前将算法输出分辨率降回 `320x240`，面积阈值和 ROI 边距也恢复为 `rect_08.py` 的量级，显示端将二值输出拉伸到 LCD 全屏。
*   **[rect09.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect09.py)** (Sensor id=2 + LAB 阈值动态 ROI IDE 版)
    *   **配置**：`Sensor(id=2, width=1280, height=720, fps=90)` 基础模式，输出 `320x240 RGB565`，IDE 虚拟显示输出
    *   **描述**：基于 `rect09_lcd.py` 的电脑显示版本，采集路径、LAB 阈值、动态 ROI、全屏形态学滤波、**全屏每帧搜索（取消降频且门槛阈值降至 8000）**、GPIO2 输出和恢复逻辑保持一致；显示端从 `Display.ST7701` 改为 `Display.VIRT`，通过 `to_ide=True` 将二值处理后的画面传输到电脑 IDE 显示。为保证实时性，当前将算法输出分辨率降回 `320x240`，面积阈值和 ROI 边距也恢复为 `rect_08.py` 的量级。
*   **[rect_08_1.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect_08_1.py)** (LAB 阈值彩色预览版)
    *   **配置**：`320x240 RGB565` (彩色采集)
    *   **描述**：`rect_08.py` 的彩色显示版本，复用其 LAB 反相二值化、动态 ROI、GPIO2 输出和异常恢复策略，但将识别结果绘制回 RGB565 原图显示。该文件依赖同目录下的 `rect_08.py`，适合在调试阶段同时观察真实彩色画面和识别框线。
*   **[rect_08_2.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect_08_2.py)** (LAB 阈值无形态学滤波版)
    *   **配置**：`320x240 RGB565` (彩色采集)
    *   **描述**：基于 `rect_08.py` 的对照测试版本，保留 LAB 反相二值化、动态 ROI、GPIO2 输出、候选矩形调试、全屏搜索降频和 `MemoryError` 恢复逻辑，但删除 `dilate()` / `erode()` 形态学闭运算，用于判断形态学滤波是否影响当前 LAB 矩形识别稳定性。
*   **[rect_08_3.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/rect_08_3.py)** (LAB 阈值 MemoryError 退避恢复版)
    *   **配置**：`320x240 RGB565` (彩色采集)
    *   **描述**：基于 `rect_08.py` 的稳健恢复版本，保留 LAB 反相二值化、形态学滤波、动态 ROI 和 GPIO2 输出。针对 fast frame buffer stack 溢出，新增退避恢复机制：发生 `MemoryError` 后跳过若干帧 `find_rects()`，连续溢出时逐步增加跳帧数；恢复期临时提高 `find_rects` 阈值，并改为稀疏全屏搜索，避免反复探测同一个触发溢出的局部 ROI。当前关闭候选调试绘制和屏幕文字叠加，并过滤贴近画面边缘的候选矩形，减少误锁半截目标和 `draw_string` 警告噪声。

### 2. 辅助测试与主入口程序

*   **[main.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/main.py)** (开机自启程序)
    *   **描述**：K230 芯片上电自动运行 the 入口代码，当前内容映射至 `rect_03.py`，实现设备通电后自动运行灰度版目标追踪。
*   **[test_rect_example_lcd.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/test_rect_example_lcd.py)** (官方 find_rects LCD 全屏测试版)
    *   **配置**：`320x240 RGB565` 摄像头采集，`800x480 ST7701` LCD 输出
    *   **描述**：由 `examples/11-Feature-Detection/find_rects.py` 改写而来，保留官方 `img.find_rects(threshold=10000)` 矩形检测与红框/绿角点绘制逻辑；显示端改为 LCD，并复用一张 `800x480 RGB565` 显示帧，通过 `draw_image(..., x_scale, y_scale)` 将 `320x240` 识别画面拉伸到 LCD 全屏。
*   **[test_rect_wire.py](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/test_rect_wire.py)** (连接线稳定性排查版)
    *   **配置**：默认 `Sensor(id=2, width=1280, height=720, fps=90)`，输出 `640x480 GRAYSCALE`，`800x480 ST7701` LCD 输出，显示帧率为 `15 FPS`
    *   **描述**：由官方 `find_rects.py` 改写而来，用于排查摄像头通过连接线接入后蓝屏的问题。当前默认向 `face_pose.py` 和 23-CV_Lite 例程的初始化方式靠拢，显式使用 `Sensor(id=2)` 和 `1280x720` 基础 sensor mode；同时关闭 IDE 虚拟显示链路，并重新启用 `find_rects()`。为了提供明确画面反馈，显示前会将灰度帧转换为 RGB565、叠加帧号，并通过 `draw_image(..., x_scale, y_scale)` 拉伸到 LCD 全屏。顶部提供 `ENABLE_FIND_RECTS`、`FULLSCREEN_SCALE`、`USE_GRAYSCALE` 等开关，可继续做采集、显示和算法的分项排查。

### 3. 设计方案与技术文档

*   **[程序设计方案.md](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/程序设计方案.md)**
    *   **描述**：记录项目整体架构（眼在手上方案）、视觉算法选型（投影交点法定位靶心、透视变换拟合6cm圆轨迹）以及串口 UART 通信帧协议（8字节带校验和）。
*   **[踩坑记录_01与02架构对比分析.md](file:///D:/work_office/code/keil_project/2026_pretest/视觉/K230程序设计/踩坑记录_01与02架构对比分析.md)**
    *   **描述**：针对 K230 硬件多媒体缓冲池 (VB Pool) 和通道冲突导致 Snapshot 失败的技术问题进行了深度复盘，并阐述了“单通道采集+软件 Copy 后处理”的稳定性设计原则。

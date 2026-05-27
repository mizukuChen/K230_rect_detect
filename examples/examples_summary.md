# CanMV K230 AI 开发板例程功能总结

本文档总结了 `D:\work_office\code\keil_project\2026_pretest\视觉\examples` 目录下各个例程的功能。

## 目录树及功能说明

```text
examples/
├── 01-Micropython-Basics/      # MicroPython 基础例程
│   ├── demo_crc16.py           # CRC16 校验演示
│   ├── demo_files.py           # 文件操作演示
│   ├── demo_fs_info.py         # 文件系统信息获取
│   ├── demo_globals.py         # 全局变量使用演示
│   ├── demo_json.py            # JSON 数据解析与序列化
│   ├── demo_logging.py         # 日志系统演示
│   ├── demo_sha256.py          # SHA256 哈希计算
│   ├── demo_sys_info.py        # 系统信息获取
│   ├── demo_thread.py          # 多线程功能演示
│   ├── demo_time.py            # 时间与定时功能
│   ├── demo_tree.py            # 目录树打印演示
│   ├── demo_view_mem.py        # 内存查看演示
│   ├── demo_yield.py           # 协程 yield 基本用法
│   └── demo_yield_task.py      # 基于 yield 的任务调度
├── 02-Media/                   # 多媒体例程 (音视频)
│   ├── acodec.py               # 音频编解码演示
│   ├── ai_rtsp.py              # AI 结果推流演示
│   ├── audio.py                # 音频录制与播放
│   ├── audio_pdm.py            # PDM 数字麦克风演示
│   ├── mp4demuxer.py           # MP4 解复用 (提取音视频)
│   ├── mp4muxer.py             # MP4 复用 (封装音视频)
│   ├── rtsp_server.py          # RTSP 服务器推流演示
│   ├── uvc.py                  # UVC (USB 摄像头) 功能演示
│   ├── uvc_with_csc.py         # 带色彩空间转换的 UVC 演示
│   ├── video_decoder.py        # 视频解码演示
│   ├── video_encoder.py        # 视频编码演示
│   ├── video_player.py         # 视频播放器演示
│   └── virtual_wbc_rtsp.py     # 虚拟显示推流演示
├── 03-Machine/                 # 硬件外设控制例程
│   ├── adc.py                  # 模数转换器 (ADC) 演示
│   ├── dht.py                  # DHT11/22 温湿度传感器驱动
│   ├── display_and_touch.py    # 显示与触摸屏综合演示
│   ├── ds18b20.py              # DS18B20 温度传感器驱动
│   ├── fft.py                  # 快速傅里叶变换 (FFT) 演示
│   ├── fpioa.py                # 引脚复用 (FPIOA) 设置
│   ├── i2c_24c32.py            # I2C EEPROM (24C32) 读写
│   ├── i2c_mpu6050.py          # I2C 六轴传感器 (MPU6050) 驱动
│   ├── i2c_slave.py            # I2C 从机模式演示
│   ├── i2c_ssd1306.py          # I2C OLED 显示器 (SSD1306) 驱动
│   ├── pin.py                  # GPIO 基本输入输出
│   ├── pin_irq.py              # GPIO 中断演示
│   ├── pwm.py                  # 脉冲宽度调制 (PWM) 演示
│   ├── pwm_servo.py            # PWM 控制舵机演示
│   ├── read_chipid.py          # 读取芯片 ID
│   ├── read_chip_temperature.py # 读取芯片内部温度
│   ├── reset.py                # 系统复位演示
│   ├── rtc.py                  # 实时时钟 (RTC) 演示
│   ├── spi.py                  # SPI 通信演示
│   ├── spi_lcd_show.py         # SPI 接口 LCD 显示演示
│   ├── spi_lcd_show_custom_screen.py # SPI LCD 自定义屏幕演示
│   ├── timer.py                # 定时器 (Timer) 演示
│   ├── touch.py                # 触摸屏驱动演示
│   ├── touch_user.py           # 用户自定义触摸处理
│   ├── uart.py                 # 串口 (UART) 通信演示
│   ├── uart1.py                # 串口 1 演示
│   ├── uart2.py                # 串口 2 演示
│   ├── wdt.py                  # 看门狗 (WDT) 演示
│   └── ws2812.py               # WS2812 彩灯控制
├── 04-Cipher/                  # 加密与哈希例程
│   ├── ucryptolib_aes*.py      # AES 对称加密演示 (ECB/CBC/CTR)
│   └── uhashlib_*.py           # MD5/SHA1/SHA256 哈希演示
├── 05-AI-Demo/                 # 视觉 AI 算法演示
│   ├── body_seg.py             # 人体分割
│   ├── dynamic_gesture.py      # 动态手势识别
│   ├── eye_gaze.py             # 视线估计
│   ├── face_detection.py       # 人脸检测
│   ├── face_detect_yunet.py    # 使用 YuNet 的人脸检测
│   ├── face_landmark.py        # 人脸关键点检测
│   ├── face_liveness_rgb.py    # 基于 RGB 的活体检测
│   ├── face_mesh.py            # 人脸网格
│   ├── face_parse.py           # 人脸解析 (各部位分割)
│   ├── face_pose.py            # 人脸姿态估计
│   ├── face_recognition.py     # 人脸识别
│   ├── face_registration.py    # 人脸注册
│   ├── falldown_detect.py      # 跌倒检测
│   ├── finger_guessing.py      # 猜拳识别
│   ├── hand_detection.py       # 手部检测
│   ├── hand_keypoint_detection.py # 手部关键点检测
│   ├── hand_recognition.py     # 手势识别
│   ├── keyword_spotting.py     # 语音关键字识别 (KWS)
│   ├── license_plate_det*.py   # 车牌检测与识别 (YOLO/常规)
│   ├── nanotracker.py          # 目标跟踪 (NanoTracker)
│   ├── object_detect_yolov8n.py # YOLOv8n 目标检测
│   ├── ocr_det.py              # OCR 文字检测
│   ├── ocr_rec.py              # OCR 文字识别
│   ├── person_detection.py     # 行人检测
│   ├── person_keypoint_detect.py # 人体关键点检测
│   ├── puzzle_game.py          # 拼图小游戏 (AI 交互)
│   ├── segment_yolov8n.py      # YOLOv8n 语义分割
│   ├── self_learning.py        # 自学习分类
│   ├── tts_zh.py               # 中文文本转语音 (TTS)
│   ├── yolo11n_obb.py          # YOLO11n 旋转框检测
│   └── yolov8n_obb.py          # YOLOv8n 旋转框检测
├── 06-Display/                 # 显示输出配置例程
│   ├── display_hdmi.py         # HDMI 输出配置
│   ├── display_lcd.py          # LCD 屏幕显示配置
│   └── display_virt.py         # 虚拟显示输出 (推流用)
├── 07-April-Tags/              # AprilTag 标签检测
│   ├── find_apriltags.py       # 基础 AprilTag 检测
│   └── find_apriltags_3d_pose.py # AprilTag 3D 姿态估计
├── 08-Codes/                   # 条码与二维码识别
│   ├── find_barcodes.py        # 条形码识别
│   ├── find_datamatrices.py    # DataMatrix 码识别
│   └── find_qrcodes.py         # 二维码识别
├── 09-Color-Tracking/          # 颜色追踪与统计
│   ├── automatic_*_tracking.py # 自动颜色阈值追踪
│   ├── black_grayscale_line_following.py # 黑色巡线演示
│   ├── image_histogram_info.py # 图像直方图信息获取
│   ├── image_statistics_info.py # 图像区域统计信息
│   └── *_color_code_tracking.py # 单/多颜色色块追踪
├── 10-Drawing/                 # 图像绘图演示
│   ├── arrow_drawing.py        # 绘制箭头
│   ├── circle_drawing.py       # 绘制圆形
│   ├── cross_drawing.py        # 绘制十字
│   ├── image_drawing.py        # 图像叠加绘制
│   ├── line_drawing.py         # 绘制直线
│   ├── rectangle_drawing.py    # 绘制矩形
│   └── text_drawing.py         # 绘制文本
├── 11-Feature-Detection/       # 特征检测算法
│   ├── edges.py                # 边缘检测 (Canny/Sobel)
│   ├── find_blobs.py           # 色块检测 (Blobs)
│   ├── find_lines.py           # 直线检测 (Hough)
│   ├── find_rects.py           # 矩形检测
│   ├── hog.py                  # HOG 特征提取
│   ├── lbp.py                  # LBP 特征提取
│   └── linear_regression_fast.py # 快速线性回归 (用于巡线)
├── 12-Image-Filters/           # 图像滤镜与变换
│   ├── blur_filter.py          # 模糊滤镜
│   ├── color_binary_filter.py  # 彩色二值化
│   ├── edge_filter.py          # 边缘增强滤镜
│   ├── erode_and_dilate.py     # 腐蚀与膨胀 (形态学)
│   ├── gamma_correction.py     # Gamma 校正
│   ├── histogram_equalization.py # 直方图均衡化
│   ├── lens_correction.py      # 镜头畸变校正
│   ├── perspective_correction.py # 透视校正
│   └── rotation_correction.py  # 旋转校校正
├── 14-Socket/                  # 网络通信例程
│   ├── http_client.py          # HTTP 客户端请求
│   ├── http_server.py          # HTTP 服务器响应
│   ├── network_lan.py          # 以太网 (LAN) 配置
│   ├── network_wlan_sta.py     # Wi-Fi 客户端 (STA) 连接
│   ├── tcp_client.py           # TCP 客户端
│   ├── tcp_server.py           # TCP 服务器
│   └── udp_server.py           # UDP 服务器
├── 15-LVGL/                    # LVGL 图形库演示
│   ├── lvgl_demo.py            # LVGL 基础组件演示
│   └── lvgl_touch_demo.py      # LVGL 触摸交互演示
├── 16-AI-Cube/                 # AI-Cube 应用级封装演示
│   ├── ClassificationApp.py    # 图像分类应用
│   ├── DetectionApp.py         # 目标检测应用
│   └── SegmentationApp.py      # 语义分割应用
├── 17-Sensor/                  # 摄像头传感器高级控制
│   ├── camera_auto_focus_lcd.py # 自动对焦演示
│   ├── camera_mirror_flip.py   # 镜像与翻转设置
│   └── camera_snapshot_and_save.py # 拍照并保存到 SD 卡
├── 18-NNCase/                  # NNCase (KPU) 底层调用例程
│   ├── kpu.py                  # KPU 基本推理流程演示
│   └── ai2d+kpu.py             # AI2D 预处理与 KPU 推理结合
├── 19-CloudPlatScripts/        # 云平台部署配套脚本
│   └── deploy_*.py             # 各类模型在云端的部署演示
├── 20-YOLO-Module-Examples/    # YOLO 系列模型专项演示
│   └── yolo*_det_video.py      # YOLOv5/v8/v11 检测演示
├── 21-AI-With-Others/          # AI 与其他模块综合应用
│   ├── ai_lvgl.py              # AI 结果在 LVGL 界面显示
│   ├── ai_uart.py              # AI 结果通过串口发送
│   └── ai_save_mp4.py          # AI 识别过程保存为 MP4
├── 22-Others/                  # 其他杂项例程
│   └── kpu_run_fps.py          # KPU 运行帧率测试
├── 23-CV_Lite/                 # CV Lite 视觉库精简版演示
│   └── rgb888_find_*.py        # 基于 RGB888 格式的各类视觉检测
├── 99-HelloWorld/              # 入门例程
│   └── helloworld.py           # 打印 "Hello World" 并显示彩虹色
├── kmodel/                     # AI 模型文件 (.kmodel 集合)
└── utils/                      # 工具类及资源文件 (词典、图片、音频)
```

## 总结

这些例程涵盖了从基础硬件控制、网络通信到高级 AI 视觉算法的方方面面，是基于 K230 芯片进行二次开发的重要参考资源。

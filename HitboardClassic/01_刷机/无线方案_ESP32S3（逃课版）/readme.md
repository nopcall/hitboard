# Hitbox 无线系统 - 三步搭建教程

## 准备工作（所有设备共用）

**所需硬件**：两块 ESP32-S3 开发板。

### 1. 安装 Arduino IDE
- 下载安装 [Arduino IDE](https://www.arduino.cc/en/software)
- 打开后，进入 **文件 → 首选项**，在 **附加开发板管理器网址** 添加：
  ```
  https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
  ```
- 进入 **工具 → 开发板 → 开发板管理器**，搜索 `esp32`，安装 **esp32 by Espressif Systems**（版本 2.0.14 或更高）

### 2. 安装 Python 环境
- 安装 Python 3.8+（[官网下载](https://www.python.org/downloads/)），勾选 **Add Python to PATH**
- 打开命令提示符（Windows）或终端（macOS/Linux），执行：
  ```bash
  pip install flask pyserial vgamepad
  ```
- **Windows 用户**还需安装 ViGEmBus 驱动（[下载地址](https://github.com/nefarius/ViGEmBus/releases)），安装后重启电脑

### 3. 准备文件
- `server.ino` → 接收端代码（ESP‑NOW 接收 + 串口输出）
- `client.ino` → 发射端代码（读取按键 + ESP‑NOW 发送 + 串口输出，支持有线/无线同时工作）
- `HitboardJoyCon.py` → PC 端 Python 程序（解析串口、模拟手柄、Web 配置界面）

---

## 第一步：烧录接收端并获取 MAC 地址

1. **打开接收端代码**  
   用 Arduino IDE 打开 `server.ino`。

2. **烧录一个获取 MAC 地址的小程序**（临时）  
   新建 Arduino 文件，粘贴以下代码：
   ```cpp
   #include <WiFi.h>
   void setup() {
     Serial.begin(115200);
     WiFi.mode(WIFI_STA);
     Serial.print("MAC Address: ");
     Serial.println(WiFi.macAddress());
   }
   void loop() {}
   ```
   选择开发板 **ESP32S3 Dev Module**，选择正确的端口，点击 **上传**。  
   上传后打开 **串口监视器**（波特率 115200），记录下显示的 MAC 地址（例如 `24:EC:4A:11:9F:3C`）。**这个地址稍后要填入发射端代码**。

3. **烧录正式的接收端程序**  
   重新打开 `server.ino`（接收端正式代码），点击 **上传**。  
   上传完成后保持接收端连接电脑（此时它只是串口设备，不会显示为手柄）。

> **接收端特点**：活动时以 **1000Hz** 轮询，无按键 60 秒后自动降频至 10Hz 省电。

---

## 第二步：烧录发射端

1. 用 Arduino IDE 打开 `client.ino`。

2. **修改接收端 MAC 地址**  
   找到代码中的：
   ```cpp
   uint8_t receiverMac[] = {0x24, 0xEC, 0x4A, 0x11, 0x9F, 0x3C};
   ```
   将里面的值替换成**你刚才记录的接收端 MAC 地址**（格式：每两位加 `0x`，用逗号分隔）。

3. （可选）调整消抖延迟  
   发射端默认消抖延迟为 `0` 毫秒。如果你的按键存在机械抖动，可将代码顶部的 `DEBOUNCE_DELAY_MS` 改为 `3`～`10`。

4. 连接发射端开发板，选择 **ESP32S3 Dev Module** 和对应的端口，点击 **上传**。  
   上传后打开串口监视器（115200），看到 `发送端已就绪` 即可。

> **发射端特点**：
> - 同时支持 **无线（ESP-NOW）** 和 **有线（USB 串口）** 输出，无需切换固件。
> - 活动扫描频率 **1000Hz**（1ms 间隔），无按键 60 秒后降频至 10Hz 省电。
> - 可直接通过 USB 连接 PC 使用（有线模式），也可无线发送给接收端。

---

## 第三步：运行 PC 端 Python 程序

1. 将**接收端**或**发射端**（有线模式）通过 USB 连接电脑，记下串口号（例如 `COM3` 或 `/dev/ttyUSB0`）。  
   Python 程序会自动扫描，如果找不到可手动设置。

2. 打开 `HitboardJoyCon.py`，如需手动指定串口，修改：
   ```python
   SERIAL_PORT = 'COM3'   # Windows 示例
   # 或 SERIAL_PORT = '/dev/ttyUSB0'   # Linux/macOS
   ```

3. 打开命令提示符/终端，进入 `HitboardJoyCon.py` 所在目录，执行：
   ```bash
   python HitboardJoyCon.py
   ```
   看到输出：
   ```
   Web 界面：http://localhost:5000
   串口 ... 已打开
   ```
   即启动成功。

4. 浏览器访问 `http://localhost:5000`：
   - 按下 Hitbox 按键，网页上对应的 Btn 会高亮。
   - 为每个物理按键配置 1~2 个手柄输出（例如把 Btn0 映射到 Xbox 的 A 键）。
   - 切换 Xbox / Switch / PS5 显示模式（仅改变网页上的按键名称）。

5. 此时系统会多出一个虚拟 Xbox 360 手柄，在游戏控制器中即可测试。

---

## 使用说明

- **无线模式**：发射端不接 USB（或只供电），接收端接电脑 → PC 读取接收端串口。
- **有线模式**：发射端直接接电脑 → PC 读取发射端串口（发射端会同时发出无线信号，但无接收端时忽略）。
- 两种模式**无需重新烧录**，即插即用。

---

**完整流程结束。** 无需安装额外 Arduino 库，三个文件各自发挥作用。



发射功率设置说明
宏 TX_POWER 的值对应 0.25 dBm 步进，实际输出功率 = TX_POWER * 0.25 dBm。

常用值参考：

20 → 5 dBm（约 3.16 mW）—— 默认，室内近距离足够，辐射很低。

40 → 10 dBm（约 10 mW）—— 标准功率（ESP‑NOW 默认约 20 dBm？实际上默认最高可达 84，即 21 dBm）。

4 → 1 dBm（约 1.26 mW）—— 极低功率，适合更衣室等极小范围。

84 → 21 dBm（约 125 mW）—— 最大功率，不推荐（辐射较大）。

修改 TX_POWER 后重新上传即可生效，无需改动其他部分。


功率与距离的简单对应（开阔环境）
TX_POWER	功率 (dBm)	实用距离（室内）
4	1 dBm	< 2 米
12	3 dBm	2~3 米
20	5 dBm	3~5 米（推荐）
40	10 dBm	5~10 米
84	21 dBm	> 15 米（过强）
你可以根据实际使用距离调整，在保证稳定连接的前提下尽量降低功率，以减少辐射和功耗。

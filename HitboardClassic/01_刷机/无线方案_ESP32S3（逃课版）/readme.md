# Hitbox 无线系统 - 三步搭建教程

准备工作：
- 两块 ESP32S3 芯片。
- 项目中的代码拷贝到本地。

### 第一步：烧录发射端、接收端程序。
先获取它们的 Mac 地址。
1.  用 Arduino IDE 新建一个项目。把获取 Mac 地址的代码粘贴进去。连接 ESP32，点击 IDE 的右方向按钮，上传程序。
#include <WiFi.h>

void setup() {
  Serial.begin(115200);
  // 等待串口就绪（尤其对于 ESP32-S3 原生 USB CDC）
  delay(2000);
  
  WiFi.mode(WIFI_STA);
  
  // 确保 WiFi 已启动
  delay(100);
  
  String mac = WiFi.macAddress();
  Serial.println("=== ESP32 MAC Address ===");
  Serial.println(mac);
  Serial.println("=========================");
}

void loop() {
  // 每隔 5 秒重复打印一次，防止错过
  static unsigned long lastPrint = 0;
  if (millis() - lastPrint > 5000) {
    lastPrint = millis();
    Serial.println(WiFi.macAddress());
  }
}

点击 IDE 的串口查看按钮，看到 Mac 地址，并记录到本地备份。
把发射端的 Mac，填到接收端。
把接收端的 Mac，填到发射端。

2. 连接每块 ESP32 到电脑，分别烧录进去填完 Mac 地址的，发射端代码，和接收端代码。
这样你就得到了能读取引脚信号，并且有线或无线发送串口信息的设备。


### 第二步：把发射端装到设备里，并按引脚图接线。


### 第三步：运行 PC 端 Python 程序

0. 问 AI 的方式，在你的电脑上安装 Python 环境。

1. 在终端通过 python 命令安装需要的库：
pip install pyserial flask vgamepad pynput

2. 运行 python 程序：
把发射端或者接收端连接到电脑，终端运行：
python pc_HitboardJoyCon.py

程序会自动扫描端口，并模拟手柄、启动网页配置服务。


如果需要改键，浏览器访问 `http://localhost:5000`：
   - 按下 Hitbox 按键，网页上对应的 Btn 会高亮。
   - 为每个物理按键配置 1~2 个手柄输出（例如把 Btn0 映射到 Xbox 的 A 键）。
   - 切换 Xbox / Switch / PS5 显示模式（仅改变网页上的按键名称）。



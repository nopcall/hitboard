import json
import serial
import serial.tools.list_ports
import threading
import time
import os
import logging
from flask import Flask, render_template_string, request, jsonify
from vgamepad import VX360Gamepad, XUSB_BUTTON

# 关闭 Flask 请求日志
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# -------------------- 自动扫描串口 --------------------
def find_serial_port():
    for port in serial.tools.list_ports.comports():
        if "Bluetooth" in (port.description or "").lower():
            continue
        if "USB" in (port.description or "").lower() or "COM" in port.device or "tty.usbmodem" in port.device:
            return port.device
    return None

SERIAL_PORT = find_serial_port()
if SERIAL_PORT is None:
    print("错误：未找到可用串口，请检查接收器连接。")
    exit(1)

BAUDRATE = 460800
MAPPING_FILE = 'mapping.json'

# -------------------- 物理按键顺序 (Btn0~17) --------------------
PHYSICAL_KEYS = [
    "up", "down", "left", "right",     # 0-3
    "a", "b", "x", "y",                # 4-7
    "lb", "rb",                        # 8-9
    "lt", "rt",                        # 10-11
    "start", "select", "home", "capture", # 12-15
    "ls", "rs"                         # 16-17
]
BTN_COUNT = len(PHYSICAL_KEYS)

# -------------------- 内部键名（存储和输出用） --------------------
INTERNAL_KEYS = [
    "None",
    "A", "B", "X", "Y",
    "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT",
    "LB", "RB",
    "LT", "RT",
    "START", "BACK", "HOME",
    "LS", "RS"
]

# 外部显示名（每个平台对应 INTERNAL_KEYS 的顺序）
XBOX_DISPLAY = [
    "None",
    "A", "B", "X", "Y",
    "↑", "↓", "←", "→",
    "LB", "RB",
    "LT", "RT",
    "菜单", "视图", "Xbox键",
    "LS", "RS"
]

SWITCH_DISPLAY = [
    "None",
    "B", "A", "Y", "X",
    "↑", "↓", "←", "→",
    "L", "R",
    "ZL", "ZR",
    "+", "-", "HOME",
    "左摇杆", "右摇杆"
]

PS5_DISPLAY = [
    "None",
    "✕", "◯", "□", "△",
    "↑", "↓", "←", "→",
    "L1", "R1",
    "L2", "R2",
    "选项", "创建", "PS",
    "左摇杆/L3", "右摇杆/R3"
]

PLATFORM_DISPLAY = {
    "Xbox": XBOX_DISPLAY,
    "Switch": SWITCH_DISPLAY,
    "PS5": PS5_DISPLAY
}

# 内部键名到 Xbox 实际输出的映射
XBOX_OUTPUT_MAP = {
    "None": None,
    "A": XUSB_BUTTON.XUSB_GAMEPAD_A,
    "B": XUSB_BUTTON.XUSB_GAMEPAD_B,
    "X": XUSB_BUTTON.XUSB_GAMEPAD_X,
    "Y": XUSB_BUTTON.XUSB_GAMEPAD_Y,
    "DPAD_UP": XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
    "DPAD_DOWN": XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
    "DPAD_LEFT": XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
    "DPAD_RIGHT": XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
    "LB": XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
    "RB": XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
    "LT": "left_trigger",
    "RT": "right_trigger",
    "START": XUSB_BUTTON.XUSB_GAMEPAD_START,
    "BACK": XUSB_BUTTON.XUSB_GAMEPAD_BACK,
    "HOME": XUSB_BUTTON.XUSB_GAMEPAD_GUIDE,
    "LS": XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
    "RS": XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
}

# -------------------- 默认映射 --------------------
DEFAULT_MAPPING = {
    "up":    ["DPAD_UP", "None"],
    "down":  ["DPAD_DOWN", "None"],
    "left":  ["DPAD_LEFT", "None"],
    "right": ["DPAD_RIGHT", "None"],
    "a":     ["A", "None"],
    "b":     ["B", "None"],
    "x":     ["X", "None"],
    "y":     ["Y", "None"],
    "lb":    ["LB", "None"],
    "rb":    ["RB", "None"],
    "lt":    ["LT", "None"],
    "rt":    ["RT", "None"],
    "start": ["START", "None"],
    "select":["BACK", "None"],
    "home":  ["HOME", "None"],
    "capture":["BACK", "None"],
    "ls":    ["LS", "None"],
    "rs":    ["RS", "None"],
}

# -------------------- 加载 / 保存 --------------------
def load_config():
    mapping = {}
    platform = "Xbox"
    if os.path.exists(MAPPING_FILE):
        try:
            with open(MAPPING_FILE, 'r') as f:
                data = json.load(f)
            platform = data.get("platform", "Xbox")
            # 加载映射（内部键名）
            saved = data.get("mappings", {})
            for key in PHYSICAL_KEYS:
                val = saved.get(key, DEFAULT_MAPPING.get(key, ["A", "None"]))
                if isinstance(val, str):
                    val = [val, "None"] if val != "None" else ["None", "None"]
                elif isinstance(val, list):
                    val = val[:2]
                    while len(val) < 2:
                        val.append("None")
                else:
                    val = ["None", "None"]
                # 过滤无效内部键名
                val = [v if v in INTERNAL_KEYS else "None" for v in val]
                mapping[key] = val
        except Exception as e:
            print(f"加载配置失败：{e}")
    else:
        for key in PHYSICAL_KEYS:
            mapping[key] = DEFAULT_MAPPING.get(key, ["None", "None"])[:]
    return mapping, platform

def save_config(mapping, platform):
    data = {
        "mappings": mapping,
        "platform": platform
    }
    with open(MAPPING_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# 当前全局状态
current_mapping, current_platform = load_config()

# -------------------- 实时按钮状态 (Web 高亮) --------------------
current_button_states = [False] * BTN_COUNT
state_lock = threading.Lock()

# -------------------- 手柄输出 --------------------
def apply_action(gamepad, internal_key, press):
    if internal_key is None or internal_key == "None":
        return
    target = XBOX_OUTPUT_MAP.get(internal_key)
    if target is None:
        return
    if target == "left_trigger":
        gamepad.left_trigger_float(1.0 if press else 0.0)
    elif target == "right_trigger":
        gamepad.right_trigger_float(1.0 if press else 0.0)
    else:
        if isinstance(target, int):
            if press:
                gamepad.press_button(target)
            else:
                gamepad.release_button(target)

# -------------------- Flask Web 界面 --------------------
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Hitboard 按键配置</title>
    <meta charset="utf-8">
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 20px auto; padding: 0 20px; }
        .section { margin: 24px 0; }
        .btn-grid { display: grid; grid-template-columns: repeat(9, 1fr); gap: 8px; }
        .btn-item { text-align: center; padding: 8px 4px; background: #e0e0e0; border-radius: 6px; font-size: 14px; }
        .btn-item.active { background: #1e2b3c; color: white; }
        .platform-nav { display: flex; gap: 0; margin: 8px 0 16px 0; }
        .platform-btn { padding: 8px 24px; border: 2px solid #1e2b3c; background: white; color: #1e2b3c; cursor: pointer; font-size: 14px; }
        .platform-btn:first-of-type { border-radius: 8px 0 0 8px; }
        .platform-btn:last-of-type { border-radius: 0 8px 8px 0; }
        .platform-btn.active { background: #1e2b3c; color: white; }
        .row { display: flex; align-items: center; margin: 5px 0; }
        .key { width: 60px; font-weight: bold; }
        select { margin-right: 8px; padding: 4px; }
        button { padding: 12px 30px; background: #1e2b3c; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; }
        button:hover { opacity: 0.9; }
        h3 { margin-bottom: 5px; }
    </style>
</head>
<body>
    <h1>Hitboard 按键配置</h1>

    <!-- 按键查询面板 -->
    <div class="section">
        <h3>按键查询（按下对应的按键，高亮确认btn号）</h3>
        <div class="btn-grid" id="btnGrid">
            {% for i in range(btn_count) %}
            <div class="btn-item" id="btn{{i}}">Btn{{i}}</div>
            {% endfor %}
        </div>
    </div>

    <!-- 平台切换 -->
    <h3>选择手柄确定按键名称</h3>
    <div class="platform-nav">
        {% for p in platforms %}
        <div class="platform-btn {% if p == platform %}active{% endif %}" data-platform="{{p}}" onclick="switchPlatform('{{p}}')">{{p}}</div>
        {% endfor %}
    </div>

    <!-- 手柄按键映射 -->
    <div class="section">
        <h3>手柄按键映射（每个按键最多两个输出）</h3>
        <div id="mappingArea">
            {% for i in range(btn_count) %}
            <div class="row">
                <span class="key">Btn{{i}}</span>
                <select id="map_{{i}}_1">
                    {% for opt in display_options %}
                    <option value="{{ internal_keys[loop.index0] }}" {% if current_mapping[key_list[i]][0] == internal_keys[loop.index0] %}selected{% endif %}>{{ opt }}</option>
                    {% endfor %}
                </select>
                <select id="map_{{i}}_2">
                    {% for opt in display_options %}
                    <option value="{{ internal_keys[loop.index0] }}" {% if current_mapping[key_list[i]][1] == internal_keys[loop.index0] %}selected{% endif %}>{{ opt }}</option>
                    {% endfor %}
                </select>
            </div>
            {% endfor %}
        </div>
        <button onclick="saveSettings()">保存配置</button>
        <p id="status"></p>
    </div>

    <script>
        const btnCount = {{ btn_count }};

        async function pollStatus() {
            try {
                const resp = await fetch('/api/status');
                const data = await resp.json();
                const states = data.states || [];
                for (let i = 0; i < btnCount; i++) {
                    const el = document.getElementById('btn' + i);
                    if (el) {
                        if (states[i]) el.classList.add('active');
                        else el.classList.remove('active');
                    }
                }
            } catch(e) {}
            setTimeout(pollStatus, 20);
        }

        async function switchPlatform(platform) {
            document.querySelectorAll('.platform-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.platform === platform);
            });
            await fetch('/api/platform', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({platform: platform})
            });
            location.reload();
        }

        async function saveSettings() {
            let mappings = {};
            const keys = {{ key_list | tojson }};
            keys.forEach((key, idx) => {
                const sel1 = document.getElementById('map_' + idx + '_1');
                const sel2 = document.getElementById('map_' + idx + '_2');
                if (sel1 && sel2) mappings[key] = [sel1.value, sel2.value];
            });
            const resp = await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mappings: mappings})
            });
            const data = await resp.json();
            document.getElementById('status').innerText = data.status;
        }

        pollStatus();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    # 获取当前平台的显示名称列表
    display_opts = PLATFORM_DISPLAY[current_platform]
    # 传递内部键名列表给模板，以便 value 使用
    return render_template_string(
        HTML_TEMPLATE,
        key_list=PHYSICAL_KEYS,
        btn_count=BTN_COUNT,
        display_options=display_opts,          # 显示文本
        internal_keys=INTERNAL_KEYS,           # 内部值
        current_mapping=current_mapping,       # 内部键名映射
        platforms=["Xbox", "Switch", "PS5"],
        platform=current_platform
    )

@app.route('/api/status')
def get_status():
    with state_lock:
        states = list(current_button_states)
    return jsonify({"states": states})

@app.route('/api/platform', methods=['POST'])
def set_platform():
    global current_platform
    data = request.get_json()
    if data and data.get("platform") in ["Xbox", "Switch", "PS5"]:
        current_platform = data["platform"]
        save_config(current_mapping, current_platform)
        return jsonify({"status": f"已切换到 {current_platform}"})
    return jsonify({"status": "无效平台"}), 400

@app.route('/api/config', methods=['POST'])
def update_config():
    global current_mapping
    data = request.get_json()
    if not data:
        return jsonify({"status": "无效数据"}), 400

    new_mappings = data.get("mappings", {})
    for key in PHYSICAL_KEYS:
        vals = new_mappings.get(key, ["None", "None"])
        if isinstance(vals, str):
            vals = [vals, "None"] if vals != "None" else ["None", "None"]
        elif isinstance(vals, list):
            vals = vals[:2]
        while len(vals) < 2:
            vals.append("None")
        # 确保是有效的内部键名
        vals = [v if v in INTERNAL_KEYS else "None" for v in vals]
        current_mapping[key] = vals

    save_config(current_mapping, current_platform)
    print(f"[配置] 已保存新映射 (平台: {current_platform})")
    return jsonify({"status": "配置已保存"})

def run_web():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# -------------------- 主循环 --------------------
def main_loop():
    global current_button_states
    gamepad = VX360Gamepad()
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.1)
        print(f"串口 {SERIAL_PORT} 已打开")
    except Exception as e:
        print(f"串口失败: {e}")
        return

    prev_states = [False] * BTN_COUNT
    try:
        while True:
            line = ser.readline()
            if not line:
                continue
            raw = line.decode('utf-8', errors='ignore').strip()
            if len(raw) != 18:
                continue
            cur_states = [c == '1' for c in raw]

            with state_lock:
                current_button_states = cur_states[:]

            for i, key in enumerate(PHYSICAL_KEYS):
                if cur_states[i] != prev_states[i]:
                    press = cur_states[i]
                    targets = current_mapping.get(key, ["None", "None"])
                    # 构造显示用的名称（根据当前平台）
                    display_names = []
                    for internal in targets:
                        if internal != "None":
                            try:
                                idx = INTERNAL_KEYS.index(internal)
                                display_names.append(PLATFORM_DISPLAY[current_platform][idx])
                            except ValueError:
                                display_names.append(internal)
                    if display_names:
                        print(f"[{'按' if press else '松'}] Btn{i}: {', '.join(display_names)}")
                    else:
                        print(f"[{'按' if press else '松'}] Btn{i}: (无绑定)")

                    # 执行输出
                    for internal in targets:
                        apply_action(gamepad, internal, press)

            prev_states = cur_states
            gamepad.update()
            time.sleep(0.001)

    except KeyboardInterrupt:
        print("\n退出")
    finally:
        ser.close()
        # 释放所有按键
        for key in PHYSICAL_KEYS:
            for internal in current_mapping.get(key, ["None", "None"]):
                apply_action(gamepad, internal, False)
        gamepad.update()
        print("已重置")

if __name__ == "__main__":
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    print("Web 界面：http://localhost:5000")
    main_loop()

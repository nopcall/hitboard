import json
import serial
import serial.tools.list_ports
import threading
import time
import os
import logging
from flask import Flask, render_template_string, request, jsonify
from vgamepad import VX360Gamepad, XUSB_BUTTON
from pynput.keyboard import Controller, Key

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
KEYBOARD_MAPPING_FILE = 'keyboard_mapping.json'

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

BTN_DISPLAY_NAMES = [f"Btn{i}: {PHYSICAL_KEYS[i]}" for i in range(BTN_COUNT)]

# -------------------- 内部键名 --------------------
INTERNAL_KEYS = [
    "None",
    "A", "B", "X", "Y",
    "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT",
    "LB", "RB",
    "LT", "RT",
    "START", "BACK", "HOME",
    "LS", "RS"
]

XBOX_DISPLAY = [
    "None", "A", "B", "X", "Y",
    "↑", "↓", "←", "→",
    "LB", "RB", "LT", "RT",
    "菜单", "视图", "Xbox键", "LS", "RS"
]
SWITCH_DISPLAY = [
    "None", "B", "A", "Y", "X",
    "↑", "↓", "←", "→",
    "L", "R", "ZL", "ZR",
    "+", "-", "HOME", "左摇杆", "右摇杆"
]
PS5_DISPLAY = [
    "None", "✕", "◯", "□", "△",
    "↑", "↓", "←", "→",
    "L1", "R1", "L2", "R2",
    "选项", "创建", "PS", "左摇杆/L3", "右摇杆/R3"
]

PLATFORM_DISPLAY = {
    "Xbox": XBOX_DISPLAY,
    "Switch": SWITCH_DISPLAY,
    "PS5": PS5_DISPLAY
}

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

# -------------------- 加载 / 保存按键映射 --------------------
def load_config():
    mapping = {}
    platform = "Xbox"
    if os.path.exists(MAPPING_FILE):
        try:
            with open(MAPPING_FILE, 'r') as f:
                data = json.load(f)
            platform = data.get("platform", "Xbox")
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

current_mapping, current_platform = load_config()

# -------------------- 键盘映射配置 --------------------
def load_keyboard_mapping():
    if os.path.exists(KEYBOARD_MAPPING_FILE):
        try:
            with open(KEYBOARD_MAPPING_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_keyboard_mapping(mapping):
    with open(KEYBOARD_MAPPING_FILE, 'w') as f:
        json.dump(mapping, f, indent=2)

keyboard_mapping = load_keyboard_mapping()

# -------------------- 实时按钮状态 --------------------
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

# -------------------- 键盘模拟（组合键同时按下并保持0.1秒）--------------------
keyboard_controller = Controller()

def parse_key_combination(keys_str):
    """解析组合键字符串，返回键对象列表"""
    if not keys_str:
        return []
    parts = keys_str.lower().split('+')
    result = []
    special = {
        'ctrl': Key.ctrl,
        'alt': Key.alt,
        'shift': Key.shift,
        'win': Key.cmd,
        'space': Key.space,
        'enter': Key.enter,
        'tab': Key.tab,
        'backspace': Key.backspace,
        'delete': Key.delete,
        'up': Key.up,
        'down': Key.down,
        'left': Key.left,
        'right': Key.right,
        'pageup': Key.page_up,
        'pagedown': Key.page_down,
        'home': Key.home,
        'end': Key.end,
    }
    for f in range(1, 13):
        special[f'f{f}'] = getattr(Key, f'f{f}')
    for p in parts:
        if p in special:
            result.append(special[p])
        elif len(p) == 1 and p.isalnum():
            result.append(p)
        else:
            # 未知键原样返回（可能报错）
            result.append(p)
    return result

def trigger_keyboard_combination(combo_str, hold_duration=0.1):
    """同时按下组合键中的所有键，保持 hold_duration 秒，然后同时释放"""
    if not combo_str:
        return
    keys = parse_key_combination(combo_str)
    if not keys:
        return
    # 同时按下
    for k in keys:
        keyboard_controller.press(k)
    time.sleep(hold_duration)
    # 同时释放
    for k in reversed(keys):
        keyboard_controller.release(k)

trigger_state = {}

def keyboard_trigger_loop():
    while True:
        with state_lock:
            states = current_button_states[:]
        for idx, mapping in enumerate(keyboard_mapping):
            btn1 = mapping.get("btn1")
            btn2 = mapping.get("btn2", -1)
            keys1 = mapping.get("keys1", "")
            keys2 = mapping.get("keys2", "")
            keys3 = mapping.get("keys3", "")
            cond = states[btn1] if btn1 is not None else False
            if btn2 != -1 and btn2 is not None:
                cond = cond and states[btn2]
            was = trigger_state.get(idx, False)
            if cond and not was:
                # 将三个按键组合成一个组合键字符串（非空部分用 '+' 连接）
                combo_parts = [k for k in (keys1, keys2, keys3) if k]
                if combo_parts:
                    combo_str = '+'.join(combo_parts)
                    trigger_keyboard_combination(combo_str, hold_duration=0.1)
                trigger_state[idx] = True
            elif not cond and was:
                trigger_state[idx] = False
        time.sleep(0.01)

keyboard_thread = threading.Thread(target=keyboard_trigger_loop, daemon=True)
keyboard_thread.start()

# -------------------- Flask Web 界面 --------------------
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Hitboard 设备配置</title>
    <meta charset="utf-8">
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 20px auto; padding: 0 20px; }
        .section { margin: 24px 0; border-top: 1px solid #ccc; padding-top: 16px; }
        .btn-grid { display: grid; grid-template-columns: repeat(9, 1fr); gap: 8px; }
        .btn-item { text-align: center; padding: 8px 4px; background: #e0e0e0; border-radius: 6px; font-size: 14px; }
        .btn-item.active { background: #1e2b3c; color: white; }
        .platform-nav { display: flex; gap: 0; margin: 12px 0 8px 0; }
        .platform-btn { padding: 8px 24px; border: 2px solid #1e2b3c; background: white; color: #1e2b3c; cursor: pointer; font-size: 14px; }
        .platform-btn:first-of-type { border-radius: 8px 0 0 8px; }
        .platform-btn:last-of-type { border-radius: 0 8px 8px 0; }
        .platform-btn.active { background: #1e2b3c; color: white; }
        .row { display: flex; align-items: center; margin: 5px 0; }
        .key { width: 60px; font-weight: bold; }
        select { margin-right: 8px; padding: 6px; width: 150px; }
        button { padding: 12px 30px; background: #1e2b3c; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; }
        button:hover { opacity: 0.9; }
        h3 { margin-bottom: 5px; }
        .config-group { display: flex; flex-direction: column; gap: 12px; margin: 10px 0; }
        .config-item { display: flex; align-items: center; gap: 12px; background: #f5f5f5; padding: 8px 12px; border-radius: 8px; width: fit-content; }
        .config-item label { font-weight: bold; font-size: 0.9em; min-width: 200px; }
        .config-item select { width: 220px; margin: 0; }
        .keyboard-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        .keyboard-table th, .keyboard-table td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        .keyboard-table th { background-color: #f2f2f2; }
        .delete-btn { background-color: #e74c3c; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; }
        .add-row { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
        .kb-display { display: inline-block; min-width: 80px; cursor: pointer; background: #eee; padding: 4px 8px; border-radius: 4px; border: 1px solid #ccc; text-align: center; }
        .kb-display.recording { background: #ffeb3b; border-color: red; }
    </style>
</head>
<body>
    <h1>Hitboard 设置中心</h1>

    <!-- 设备信息配置区域 -->
    <div class="section">
        <h3>设备性能配置</h3>
        <div class="config-group">
            <div class="config-item"><label>回报率(Hz)</label><select id="polling_rate"><option value="250">250</option><option value="500">500</option><option value="800">800</option><option value="1000" selected>1000</option></select></div>
            <div class="config-item"><label>CPU频率(MHz)</label><select id="cpu_freq"><option value="80">80</option><option value="160">160</option><option value="240" selected>240</option></select></div>
            <div class="config-item"><label>发射功率</label><select id="tx_power"><option value="4">1 dBm (≈1-2米)</option><option value="12">3 dBm (≈3-5米)</option><option value="20" selected>5 dBm (≈5-8米)</option><option value="40">10 dBm (≈10-15米)</option><option value="84">21 dBm (≈20-30米)</option></select></div>
            <div class="config-item"><label>消抖(ms)</label><select id="debounce"><option value="0" selected>0</option><option value="3">3</option><option value="5">5</option><option value="10">10</option><option value="20">20</option></select></div>
            <div class="config-item"><label>电源选项（超时进入低功率模式）</label><select id="idle_timeout"><option value="5">5秒</option><option value="10">10秒</option><option value="30">30秒</option><option value="60" selected>60秒</option><option value="120">120秒</option></select></div>
        </div>
        <button onclick="saveDeviceConfig()">应用设备配置</button>
        <span id="deviceStatus" style="margin-left:10px;color:green"></span>
    </div>

    <!-- 按键查询面板 -->
    <div class="section">
        <h3>按键查询（按下对应的按键，高亮确认btn号）</h3>
        <div class="btn-grid" id="btnGrid">{% for i in range(btn_count) %}<div class="btn-item" id="btn{{i}}">Btn{{i}}</div>{% endfor %}</div>
    </div>

    <!-- 手柄按键映射 -->
    <div class="section">
        <h3>手柄按键映射（每个按键最多两个输出）</h3>
        <div class="platform-nav">{% for p in platforms %}<div class="platform-btn {% if p == platform %}active{% endif %}" data-platform="{{p}}" onclick="switchPlatform('{{p}}')">{{p}}</div>{% endfor %}</div>
        <p style="color: gray; font-size: 12px; margin-top: -5px;">切换平台仅改变按键显示名称，不影响实际输出</p>
        <div id="mappingArea" style="margin-top: 12px;">{% for i in range(btn_count) %}<div class="row"><span class="key">Btn{{i}}</span><select id="map_{{i}}_1">{% for opt in display_options %}<option value="{{ internal_keys[loop.index0] }}" {% if current_mapping[key_list[i]][0] == internal_keys[loop.index0] %}selected{% endif %}>{{ opt }}</option>{% endfor %}</select><select id="map_{{i}}_2">{% for opt in display_options %}<option value="{{ internal_keys[loop.index0] }}" {% if current_mapping[key_list[i]][1] == internal_keys[loop.index0] %}selected{% endif %}>{{ opt }}</option>{% endfor %}</select></div>{% endfor %}</div>
        <button onclick="saveSettings()">保存按键映射</button>
        <p id="status"></p>
    </div>

    <!-- 键盘按键触发配置 -->
    <div class="section">
        <h3>键盘按键触发</h3>
        <p style="color: gray; font-size: 12px;">当两个手柄按键同时按下时，触发下方三个键盘按键的组合（同时按下并保持0.1秒）。点击输入框录制单个按键，修改下拉框自动保存。</p>
        <table class="keyboard-table" id="keyboardTable">
            <thead><tr><th>手柄按键1</th><th>手柄按键2</th><th>键盘按键1</th><th>键盘按键2</th><th>键盘按键3</th><th>操作</th></thead>
            <tbody id="keyboardTbody"></tbody>
        </table>
        <div class="add-row">
            <select id="new_btn1">{% for i in range(btn_count) %}<option value="{{ i }}">{{ btn_display_names[i] }}</option>{% endfor %}</select>
            <select id="new_btn2"><option value="-1">无</option>{% for i in range(btn_count) %}<option value="{{ i }}">{{ btn_display_names[i] }}</option>{% endfor %}</select>
            <span class="kb-display" id="new_keys1_display" data-keyidx="0">未设置</span>
            <span class="kb-display" id="new_keys2_display" data-keyidx="1">未设置</span>
            <span class="kb-display" id="new_keys3_display" data-keyidx="2">未设置</span>
            <button onclick="addKeyboardMapping()">添加配置</button>
        </div>
    </div>

    <script>
        const btnCount = {{ btn_count }};
        let keyboardMapping = {{ keyboard_mapping | tojson }};
        let recordingActive = false;
        let currentRecordingContext = null;

        const keyNameMap = {
            'Control': 'ctrl', 'Alt': 'alt', 'Shift': 'shift', 'Meta': 'win',
            ' ': 'space', 'Space': 'space', 'Enter': 'enter', 'Tab': 'tab',
            'Backspace': 'backspace', 'Delete': 'delete', 'ArrowUp': 'up',
            'ArrowDown': 'down', 'ArrowLeft': 'left', 'ArrowRight': 'right',
            'PageUp': 'pageup', 'PageDown': 'pagedown', 'Home': 'home', 'End': 'end',
            'F1':'f1','F2':'f2','F3':'f3','F4':'f4','F5':'f5','F6':'f6',
            'F7':'f7','F8':'f8','F9':'f9','F10':'f10','F11':'f11','F12':'f12',
        };
        function normalizeKey(e) {
            let key = e.key;
            if (keyNameMap[key]) return keyNameMap[key];
            if (key.length === 1) return key.toLowerCase();
            return key.toLowerCase();
        }

        function startRecording(target, context) {
            if (recordingActive) return;
            recordingActive = true;
            currentRecordingContext = context;
            target.classList.add('recording');
            target.innerText = '请按下按键...';
            window.addEventListener('keydown', onRecordingKeyDown);
            window.addEventListener('keyup', onRecordingKeyUp);
        }

        function stopRecording(recordKey) {
            if (!recordingActive) return;
            window.removeEventListener('keydown', onRecordingKeyDown);
            window.removeEventListener('keyup', onRecordingKeyUp);
            const target = currentRecordingContext.target;
            target.classList.remove('recording');
            if (recordKey !== null) {
                target.innerText = recordKey;
                const { type, rowIndex, keyIdx } = currentRecordingContext;
                if (type === 'edit') {
                    const mapping = keyboardMapping[rowIndex];
                    if (mapping) {
                        if (keyIdx === 0) mapping.keys1 = recordKey;
                        else if (keyIdx === 1) mapping.keys2 = recordKey;
                        else if (keyIdx === 2) mapping.keys3 = recordKey;
                        saveKeyboardMappingToServer(keyboardMapping);
                        renderKeyboardTable();
                    }
                } else if (type === 'add') {
                    const displaySpan = target;
                    displaySpan.innerText = recordKey;
                    displaySpan.setAttribute('data-value', recordKey);
                }
            }
            recordingActive = false;
            currentRecordingContext = null;
        }

        function onRecordingKeyDown(e) {
            if (!recordingActive) return;
            e.preventDefault();
            e.stopPropagation();
            const key = normalizeKey(e);
            stopRecording(key);
        }
        function onRecordingKeyUp(e) {}

        async function saveKeyboardMappingToServer(newMapping) {
            // 只更新后端，不重新拉取（避免递归）
            await fetch('/api/keyboard_config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ action: 'sync', mapping: newMapping })
            });
        }

        async function handleMappingChange(rowIndex, field, value) {
            const mapping = keyboardMapping[rowIndex];
            if (!mapping) return;
            mapping[field] = value;
            await saveKeyboardMappingToServer(keyboardMapping);
        }

        function renderKeyboardTable() {
            const tbody = document.getElementById('keyboardTbody');
            tbody.innerHTML = '';
            for (let i = 0; i < keyboardMapping.length; i++) {
                const item = keyboardMapping[i];
                const row = tbody.insertRow();
                // 手柄按键1 下拉框
                const cell1 = row.insertCell(0);
                const sel1 = document.createElement('select');
                {{ btn_display_names | tojson }}.forEach((name, idx) => {
                    const opt = document.createElement('option');
                    opt.value = idx;
                    opt.innerText = name;
                    if (item.btn1 === idx) opt.selected = true;
                    sel1.appendChild(opt);
                });
                sel1.onchange = (function(idx) { return function(e) { handleMappingChange(idx, 'btn1', parseInt(e.target.value)); }; })(i);
                cell1.appendChild(sel1);
                // 手柄按键2 下拉框
                const cell2 = row.insertCell(1);
                const sel2 = document.createElement('select');
                const noneOpt = document.createElement('option');
                noneOpt.value = '-1';
                noneOpt.innerText = '无';
                sel2.appendChild(noneOpt);
                {{ btn_display_names | tojson }}.forEach((name, idx) => {
                    const opt = document.createElement('option');
                    opt.value = idx;
                    opt.innerText = name;
                    if (item.btn2 === idx) opt.selected = true;
                    sel2.appendChild(opt);
                });
                sel2.onchange = (function(idx) { return function(e) { handleMappingChange(idx, 'btn2', parseInt(e.target.value)); }; })(i);
                cell2.appendChild(sel2);
                // 三个键盘按键（可点击录制）
                const keys = [item.keys1, item.keys2, item.keys3];
                for (let k = 0; k < 3; k++) {
                    const cell = row.insertCell(2 + k);
                    const span = document.createElement('span');
                    span.className = 'kb-display';
                    span.innerText = keys[k] || '未设置';
                    span.onclick = (function(rowIdx, keyIdx) {
                        return function(e) {
                            e.stopPropagation();
                            if (recordingActive) return;
                            startRecording(this, { type: 'edit', rowIndex: rowIdx, keyIdx: keyIdx, target: this });
                        };
                    })(i, k);
                    cell.appendChild(span);
                }
                // 删除按钮
                const delCell = row.insertCell(5);
                const delBtn = document.createElement('button');
                delBtn.innerText = '✗ 删除';
                delBtn.className = 'delete-btn';
                delBtn.onclick = (function(idx) { return function() { deleteKeyboardMapping(idx); }; })(i);
                delCell.appendChild(delBtn);
            }
        }

        async function deleteKeyboardMapping(index) {
            const resp = await fetch('/api/keyboard_config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ action: 'delete', index: index })
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                keyboardMapping = data.mapping;
                renderKeyboardTable();
            } else {
                alert('删除失败');
            }
        }

        async function addKeyboardMapping() {
            const btn1 = parseInt(document.getElementById('new_btn1').value);
            const btn2 = parseInt(document.getElementById('new_btn2').value);
            const keys1 = document.getElementById('new_keys1_display').getAttribute('data-value') || '';
            const keys2 = document.getElementById('new_keys2_display').getAttribute('data-value') || '';
            const keys3 = document.getElementById('new_keys3_display').getAttribute('data-value') || '';
            if (!keys1 && !keys2 && !keys3) {
                alert('至少设置一个键盘按键');
                return;
            }
            const resp = await fetch('/api/keyboard_config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ action: 'add', btn1: btn1, btn2: btn2, keys1: keys1, keys2: keys2, keys3: keys3 })
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                keyboardMapping = data.mapping;
                renderKeyboardTable();
                // 清空新增区域
                document.getElementById('new_keys1_display').innerText = '未设置';
                document.getElementById('new_keys1_display').setAttribute('data-value', '');
                document.getElementById('new_keys2_display').innerText = '未设置';
                document.getElementById('new_keys2_display').setAttribute('data-value', '');
                document.getElementById('new_keys3_display').innerText = '未设置';
                document.getElementById('new_keys3_display').setAttribute('data-value', '');
            } else {
                alert('添加失败');
            }
        }

        function loadDeviceConfigFromStorage() {
            const keys = ['polling_rate', 'cpu_freq', 'tx_power', 'debounce', 'idle_timeout'];
            keys.forEach(key => { const saved = localStorage.getItem('device_'+key); if(saved) { const el = document.getElementById(key); if(el) el.value = saved; } });
        }
        function saveDeviceConfigToStorage() {
            const config = {
                polling_rate: document.getElementById('polling_rate').value,
                cpu_freq: document.getElementById('cpu_freq').value,
                tx_power: document.getElementById('tx_power').value,
                debounce: document.getElementById('debounce').value,
                idle_timeout: document.getElementById('idle_timeout').value
            };
            for (let [key, val] of Object.entries(config)) localStorage.setItem('device_'+key, val);
            return config;
        }
        async function saveDeviceConfig() {
            const config = saveDeviceConfigToStorage();
            const statusSpan = document.getElementById('deviceStatus');
            statusSpan.innerText = '发送中...';
            try {
                const resp = await fetch('/api/device_config', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(config) });
                const data = await resp.json();
                if(resp.ok) { statusSpan.innerText = '✓ 配置已应用'; setTimeout(()=>statusSpan.innerText='',2000); }
                else statusSpan.innerText = '✗ 应用失败';
            } catch(e) { statusSpan.innerText = '✗ 网络错误'; }
        }
        async function switchPlatform(platform) {
            document.querySelectorAll('.platform-btn').forEach(b=>b.classList.toggle('active',b.dataset.platform===platform));
            await fetch('/api/platform', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({platform:platform}) });
            location.reload();
        }
        async function saveSettings() {
            let mappings = {};
            const keys = {{ key_list | tojson }};
            keys.forEach((key,idx)=>{ mappings[key] = [document.getElementById('map_'+idx+'_1').value, document.getElementById('map_'+idx+'_2').value]; });
            const resp = await fetch('/api/config', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({mappings:mappings}) });
            const data = await resp.json();
            document.getElementById('status').innerText = data.status;
        }
        async function pollStatus() {
            try {
                const resp = await fetch('/api/status');
                const data = await resp.json();
                const states = data.states || [];
                for(let i=0;i<btnCount;i++) { const el = document.getElementById('btn'+i); if(el) { if(states[i]) el.classList.add('active'); else el.classList.remove('active'); } }
            } catch(e) {}
            setTimeout(pollStatus, 50);
        }
        window.addEventListener('DOMContentLoaded', () => {
            loadDeviceConfigFromStorage();
            renderKeyboardTable();
            for (let i = 0; i < 3; i++) {
                const span = document.getElementById(`new_keys${i+1}_display`);
                if (span) {
                    span.onclick = (function(keyIdx) {
                        return function(e) {
                            e.stopPropagation();
                            if (recordingActive) return;
                            startRecording(this, { type: 'add', keyIdx: keyIdx, target: this });
                        };
                    })(i);
                    if (span.innerText !== '未设置') span.setAttribute('data-value', span.innerText);
                }
            }
        });
        pollStatus();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    display_opts = PLATFORM_DISPLAY[current_platform]
    return render_template_string(
        HTML_TEMPLATE,
        key_list=PHYSICAL_KEYS,
        btn_count=BTN_COUNT,
        display_options=display_opts,
        internal_keys=INTERNAL_KEYS,
        current_mapping=current_mapping,
        platforms=["Xbox", "Switch", "PS5"],
        platform=current_platform,
        btn_display_names=BTN_DISPLAY_NAMES,
        keyboard_mapping=keyboard_mapping
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
        vals = [v if v in INTERNAL_KEYS else "None" for v in vals]
        current_mapping[key] = vals
    save_config(current_mapping, current_platform)
    return jsonify({"status": "配置已保存"})

@app.route('/api/device_config', methods=['POST'])
def device_config():
    data = request.get_json()
    print(f"[设备配置] {data}")
    return jsonify({"status": "配置已接收"})

@app.route('/api/keyboard_config', methods=['POST'])
def keyboard_config():
    global keyboard_mapping
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "无效数据"}), 400
    action = data.get("action")
    if action == "add":
        btn1 = data.get("btn1")
        btn2 = data.get("btn2", -1)
        keys1 = data.get("keys1", "")
        keys2 = data.get("keys2", "")
        keys3 = data.get("keys3", "")
        if btn1 is None:
            return jsonify({"status": "error", "message": "缺少手柄按键"}), 400
        keyboard_mapping.append({"btn1": btn1, "btn2": btn2, "keys1": keys1, "keys2": keys2, "keys3": keys3})
        save_keyboard_mapping(keyboard_mapping)
        return jsonify({"status": "ok", "mapping": keyboard_mapping})
    elif action == "delete":
        index = data.get("index")
        if index is not None and 0 <= index < len(keyboard_mapping):
            del keyboard_mapping[index]
            save_keyboard_mapping(keyboard_mapping)
            return jsonify({"status": "ok", "mapping": keyboard_mapping})
        else:
            return jsonify({"status": "error", "message": "索引无效"}), 400
    elif action == "sync":
        new_mapping = data.get("mapping")
        if new_mapping is not None:
            keyboard_mapping = new_mapping
            save_keyboard_mapping(keyboard_mapping)
            return jsonify({"status": "ok", "mapping": keyboard_mapping})
        else:
            return jsonify({"status": "error", "message": "数据无效"}), 400
    else:
        return jsonify({"status": "error", "message": "未知动作"}), 400

def run_web():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

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

                    for internal in targets:
                        apply_action(gamepad, internal, press)

            prev_states = cur_states
            gamepad.update()
            time.sleep(0.001)

    except KeyboardInterrupt:
        print("\n退出")
    finally:
        ser.close()
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

import win32gui
import win32con
import win32api
import win32process
import ctypes
import pytesseract
from PIL import ImageGrab
from pynput.mouse import Listener, Button
import threading
import time
import random
import logging

# ========== CONFIG ==========
logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(message)s')
TARGET_PROCESS = "PortalWars2Client-Win64-Shipping.exe"
OCR_BOX_RELATIVE = (1700, 960, 1900, 1016)
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
RECOIL_MULTIPLIER = 1.0
OCR_INTERVAL = 2
EXPECTED_RESOLUTION = (1920, 1080) 

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# ========== STARTUP POPUPS ==========
def auto_close_messagebox(text, title, timeout):
    def close_after_timeout():
        time.sleep(timeout)
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd:
            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  
    threading.Thread(target=close_after_timeout, daemon=True).start()
    ctypes.windll.user32.MessageBoxW(0, text, title, 0x0)

def popup_error(message, title="ERROR"):
    ctypes.windll.user32.MessageBoxW(0, message, title, 0x10) 
def popup_info(message, title="INFO"):
    ctypes.windll.user32.MessageBoxW(0, message, title, 0x40) 

def show_startup_popups():
    auto_close_messagebox("Please Don't Click Anything", "Please Wait", 3)
    time.sleep(3.2)
    popup_info("Continue To Splitgate", "Ready")

# ========== WINDOW UTILS ==========
def find_game_window():
    def callback(hwnd, hwnds):
        if win32gui.IsWindowVisible(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                proc = win32api.OpenProcess(
                    win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid
                )
                exe = win32process.GetModuleFileNameEx(proc, 0).split("\\")[-1]
                if exe.lower() == TARGET_PROCESS.lower():
                    hwnds.append(hwnd)
            except Exception:
                pass
        return True
    found = []
    win32gui.EnumWindows(callback, found)
    return found[0] if found else None

def is_window_borderless(hwnd):
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)

    borderless_style = (style & win32con.WS_BORDER == 0 and
                        style & win32con.WS_THICKFRAME == 0 and
                        style & win32con.WS_CAPTION == 0)
    popup_style = (style & win32con.WS_POPUP != 0)

    return borderless_style and popup_style

def check_resolution(hwnd):
    rect = win32gui.GetWindowRect(hwnd)
    width = rect[2] - rect[0]
    height = rect[3] - rect[1]
    logging.debug(f"Window resolution detected: {width}x{height}")
    return (width, height) == EXPECTED_RESOLUTION

# ========== RECOIL PROFILES ==========
RECOIL_PROFILES = {
    "TEMPO": {
        "pattern": [(0, 4)] * 15,
        "interval": 0.02
    },
    "SYNAPSE": {
        "pattern": [(0, 6)] * 15,
        "interval": 0.02
    },
    "TRAILBLAZER": {
        "pattern": [(0, 4)] * 15,
        "interval": 0.02
    }
}

# ========== GLOBALS ==========
recoil_active = False
current_weapon = None
recoil_thread = None
hwnd_game = None

# ========== CORE FUNCTIONS ==========
def move_mouse(dx, dy):
    jitter = random.randint(-1, 1)
    win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, int(dx * RECOIL_MULTIPLIER + jitter), int(dy * RECOIL_MULTIPLIER), 0, 0)

def safe_read_weapon_name(game_rect):
    gx, gy = game_rect[0], game_rect[1]
    x1 = gx + OCR_BOX_RELATIVE[0]
    y1 = gy + OCR_BOX_RELATIVE[1]
    x2 = gx + OCR_BOX_RELATIVE[2]
    y2 = gy + OCR_BOX_RELATIVE[3]
    img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    text = pytesseract.image_to_string(img).strip().upper()
    return ''.join(filter(str.isalnum, text))

def recoil_loop():
    global recoil_active, current_weapon
    while recoil_active:
        profile = RECOIL_PROFILES.get(current_weapon)
        if not profile:
            logging.debug("No recoil profile found, stopping recoil loop.")
            return
        pattern = profile["pattern"]
        interval = profile["interval"]
        for dx, dy in pattern:
            if not recoil_active:
                logging.debug("Recoil stopped by user.")
                return
            move_mouse(dx, dy)
            time.sleep(interval)

def on_click(x, y, button, pressed):
    global recoil_active, recoil_thread, current_weapon
    if button == Button.left:
        if pressed:
            if not recoil_active and current_weapon in RECOIL_PROFILES:
                recoil_active = True
                recoil_thread = threading.Thread(target=recoil_loop, daemon=True)
                recoil_thread.start()
                logging.debug(f"Recoil started for weapon: {current_weapon}")
        else:
            if recoil_active:
                recoil_active = False
                logging.debug("Recoil stopped due to mouse release.")

def ocr_monitor_loop():
    global current_weapon, hwnd_game
    while True:
        try:
            if not win32gui.IsWindow(hwnd_game):
                logging.error("Lost game window. Exiting OCR loop.")
                break
            rect = win32gui.GetWindowRect(hwnd_game)
            detected = safe_read_weapon_name(rect)
            if detected != current_weapon:
                if detected in RECOIL_PROFILES:
                    current_weapon = detected
                    logging.info(f"[OCR] Detected weapon: {current_weapon}")
                else:
                    logging.warning(f"[OCR] Unknown weapon: '{detected}' (no profile), recoil disabled")
                    current_weapon = None
        except Exception as e:
            logging.error(f"[OCR Error] {e}")
        time.sleep(OCR_INTERVAL)

# ========== MAIN ==========
def main():
    global hwnd_game
    show_startup_popups()
    hwnd_game = find_game_window()
    if not hwnd_game:
        popup_error(f"{TARGET_PROCESS} not running.", "ERROR")
        return

    logging.info("✅ Game window found.")

    if not is_window_borderless(hwnd_game):
        popup_error("Game window is not in borderless mode.\nPlease set your game to borderless.", "ERROR")
        return

    if not check_resolution(hwnd_game):
        popup_error(f"Game resolution is not {EXPECTED_RESOLUTION[0]}x{EXPECTED_RESOLUTION[1]}.\nPlease set the correct resolution.", "ERROR")
        return

    threading.Thread(target=ocr_monitor_loop, daemon=True).start()
    with Listener(on_click=on_click) as listener:
        listener.join()

if __name__ == "__main__":
    main()

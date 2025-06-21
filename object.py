import win32gui
import win32con
import win32api
import win32process
import ctypes
import pytesseract
from PIL import ImageGrab, ImageOps
import time
import logging
import threading

# ========== CONFIG ==========
TARGET_PROCESS = "PortalWars2Client-Win64-Shipping.exe"
OCR_BOX_RELATIVE = (1700, 960, 1900, 1016)
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

# ========== STARTUP POPUPS ==========
def auto_close_messagebox(text, title, timeout):
    def close_after_timeout():
        time.sleep(timeout)
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd:
            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
    threading.Thread(target=close_after_timeout, daemon=True).start()
    ctypes.windll.user32.MessageBoxW(0, text, title, 0x0)

def show_startup_popups():
    auto_close_messagebox("Please Don't Click Anything", "Please Wait", 3)
    time.sleep(3.2) 
    ctypes.windll.user32.MessageBoxW(0, "Continue To Splitgate", "Ready", 0x40 | 0x0)

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

def is_borderless(hwnd):
    try:
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return (left == 0 and top == 0 and (right - left) == screen_width and (bottom - top) == screen_height)
    except Exception:
        return False

# ========== OVERLAY ==========
def create_overlay(hwnd_target, rel_box):
    class_name = "SplitgateWeaponOverlay"

    def wnd_proc(hwnd, msg, wparam, lparam):
        if msg == win32con.WM_PAINT:
            hdc, ps = win32gui.BeginPaint(hwnd)
            pen = win32gui.CreatePen(win32con.PS_SOLID, 2, win32api.RGB(255, 0, 0))
            win32gui.SelectObject(hdc, pen)
            win32gui.Rectangle(hdc, 0, 0, rel_box[2] - rel_box[0], rel_box[3] - rel_box[1])
            win32gui.EndPaint(hwnd, ps)
            return 0
        elif msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = wnd_proc
    wc.lpszClassName = class_name
    hInstance = win32api.GetModuleHandle(None)
    class_atom = win32gui.RegisterClass(wc)

    game_left, game_top, _, _ = win32gui.GetWindowRect(hwnd_target)
    x = game_left + rel_box[0]
    y = game_top + rel_box[1]
    width = rel_box[2] - rel_box[0]
    height = rel_box[3] - rel_box[1]

    hwnd_overlay = win32gui.CreateWindowEx(
        win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST,
        class_atom, None, win32con.WS_POPUP,
        x, y, width, height,
        None, None, hInstance, None
    )

    win32gui.SetLayeredWindowAttributes(hwnd_overlay, 0, 100, win32con.LWA_ALPHA)
    win32gui.ShowWindow(hwnd_overlay, win32con.SW_SHOW)
    return hwnd_overlay

# ========== OCR ==========
def preprocess_image(img):
    img = img.convert("L")
    img = ImageOps.invert(img)
    img = ImageOps.autocontrast(img)
    return img

def safe_read_weapon_name(game_rect):
    gx, gy = game_rect[0], game_rect[1]
    x1 = gx + OCR_BOX_RELATIVE[0]
    y1 = gy + OCR_BOX_RELATIVE[1]
    x2 = gx + OCR_BOX_RELATIVE[2]
    y2 = gy + OCR_BOX_RELATIVE[3]

    if x2 <= x1 or y2 <= y1:
        raise ValueError("Invalid OCR box dimensions!")

    img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    processed_img = preprocess_image(img)
    return pytesseract.image_to_string(
        processed_img,
        config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-"
    ).strip()

# ========== MAIN LOOP ==========
def main():
    show_startup_popups()

    hwnd = find_game_window()
    if not hwnd:
        ctypes.windll.user32.MessageBoxW(0, f"{TARGET_PROCESS} not running.", "Error", 0x10)
        return

    if not is_borderless(hwnd):
        ctypes.windll.user32.MessageBoxW(0, "Game must be in borderless windowed mode!", "Error", 0x10)
        return

    logging.info("Game window found and validated.")
    overlay = create_overlay(hwnd, OCR_BOX_RELATIVE)

    try:
        while True:
            if not win32gui.IsWindow(hwnd):
                logging.warning("Game window lost. Retrying...")
                time.sleep(2)
                hwnd = find_game_window()
                continue

            if not win32gui.IsWindowVisible(hwnd):
                logging.debug("Game is minimized. Skipping frame.")
                time.sleep(2)
                continue

            try:
                rect = win32gui.GetWindowRect(hwnd)
                width = rect[2] - rect[0]
                height = rect[3] - rect[1]
                if width <= 0 or height <= 0:
                    logging.debug("Window invalid size (probably minimized)")
                    time.sleep(2)
                    continue

                win32gui.SetWindowPos(
                    overlay, win32con.HWND_TOPMOST,
                    rect[0] + OCR_BOX_RELATIVE[0],
                    rect[1] + OCR_BOX_RELATIVE[1],
                    0, 0,
                    win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
                )
                win32gui.RedrawWindow(overlay, None, None, win32con.RDW_INVALIDATE)

                weapon = safe_read_weapon_name(rect)
                logging.info(f"Weapon Detected: '{weapon}'")

            except Exception as e:
                logging.warning(f"OCR or overlay update failed: {e}")

            time.sleep(2)

    except KeyboardInterrupt:
        logging.info("Exiting cleanly.")
        try:
            win32gui.DestroyWindow(overlay)
        except Exception:
            pass


# ========== RUN ==========
if __name__ == "__main__":
    main()

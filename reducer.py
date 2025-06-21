# reducer.py
import win32api
import win32con
import time
import threading
from pynput.mouse import Listener, Button

RECOIL_MULTIPLIER = 1.5

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

recoil_active = False
selected_weapon = None
recoil_thread = None

def move_mouse(dx, dy):
    win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, int(dx), int(dy), 0, 0)

def recoil_loop(weapon_name):
    global recoil_active

    pattern = RECOIL_PROFILES[weapon_name]["pattern"]
    interval = RECOIL_PROFILES[weapon_name]["interval"]

    print(f"[reducer] 🎯 Starting continuous recoil for '{weapon_name}'")

    while recoil_active:
        for dx, dy in pattern:
            if not recoil_active:
                print("[reducer] 🛑 Recoil stopped mid-pattern.")
                return
            move_mouse(dx, dy)
            time.sleep(interval)

    print("[reducer] ✅ Recoil fully stopped.")

def on_click(x, y, button, pressed):
    global recoil_active, recoil_thread, selected_weapon

    if selected_weapon is None:
        return

    if button == Button.left:
        if pressed and not recoil_active:
            recoil_active = True
            recoil_thread = threading.Thread(target=recoil_loop, args=(selected_weapon,), daemon=True)
            recoil_thread.start()
        elif not pressed and recoil_active:
            recoil_active = False

def main():
    global selected_weapon

    print("🔧 Recoil Reducer (win32api version)")
    print("Available profiles:", ", ".join(RECOIL_PROFILES.keys()))
    selected_weapon = input("Enter weapon name: ").strip().upper()

    if selected_weapon not in RECOIL_PROFILES:
        print(f"❌ Invalid weapon: '{selected_weapon}'")
        return

    print("✅ Loaded. Hold LEFT CLICK to apply recoil. Press Ctrl+C to exit.")

    with Listener(on_click=on_click) as listener:
        listener.join()

if __name__ == "__main__":
    main()

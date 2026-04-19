"""Grabador y reproductor de movimientos y clics del mouse con interfaz gráfica.

Requisitos:
    pip install pynput

Uso:
    python mouse_recorder.py
"""

import json
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pynput import keyboard, mouse
from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key, KeyCode
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController


class MouseRecorderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Grabador de Mouse")
        self.root.geometry("480x420")
        self.root.resizable(False, False)

        self.events: list[dict] = []
        self.recording = False
        self.playing = False
        self.record_start_time = 0.0
        self.capture_next_key = False

        self.mouse_listener: mouse.Listener | None = None
        self.hotkey_listener: keyboard.Listener | None = None
        self.playback_thread: threading.Thread | None = None
        self.stop_playback_event = threading.Event()

        self.mouse_controller = MouseController()
        self.keyboard_controller = KeyboardController()

        self.hotkey: Key | KeyCode = Key.f9
        self.hotkey_label_var = tk.StringVar(value=self._format_key(self.hotkey))
        self.status_var = tk.StringVar(value="Listo")
        self.event_count_var = tk.StringVar(value="Eventos: 0")
        self.loop_var = tk.BooleanVar(value=False)
        self.speed_var = tk.DoubleVar(value=1.0)

        self._build_ui()
        self._start_hotkey_listener()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        padding = {"padx": 10, "pady": 6}

        title = ttk.Label(
            self.root, text="Grabador de Mouse", font=("Helvetica", 16, "bold")
        )
        title.pack(pady=10)

        status_frame = ttk.LabelFrame(self.root, text="Estado")
        status_frame.pack(fill="x", **padding)
        ttk.Label(status_frame, textvariable=self.status_var, font=("Helvetica", 11)).pack(
            anchor="w", padx=8, pady=4
        )
        ttk.Label(status_frame, textvariable=self.event_count_var).pack(
            anchor="w", padx=8, pady=(0, 4)
        )

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", **padding)
        self.record_btn = ttk.Button(
            btn_frame, text="Grabar", command=self.toggle_recording, width=14
        )
        self.record_btn.grid(row=0, column=0, padx=4, pady=4)
        self.play_btn = ttk.Button(
            btn_frame, text="Reproducir", command=self.toggle_playback, width=14
        )
        self.play_btn.grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(btn_frame, text="Limpiar", command=self.clear_events, width=14).grid(
            row=0, column=2, padx=4, pady=4
        )
        ttk.Button(btn_frame, text="Guardar...", command=self.save_events, width=14).grid(
            row=1, column=0, padx=4, pady=4
        )
        ttk.Button(btn_frame, text="Cargar...", command=self.load_events, width=14).grid(
            row=1, column=1, padx=4, pady=4
        )

        options_frame = ttk.LabelFrame(self.root, text="Opciones")
        options_frame.pack(fill="x", **padding)
        ttk.Checkbutton(
            options_frame, text="Reproducir en bucle", variable=self.loop_var
        ).grid(row=0, column=0, padx=8, pady=4, sticky="w")
        ttk.Label(options_frame, text="Velocidad:").grid(
            row=1, column=0, padx=8, pady=4, sticky="w"
        )
        speed_scale = ttk.Scale(
            options_frame,
            from_=0.25,
            to=4.0,
            orient="horizontal",
            variable=self.speed_var,
            command=self._on_speed_change,
        )
        speed_scale.grid(row=1, column=1, padx=8, pady=4, sticky="ew")
        self.speed_label = ttk.Label(options_frame, text="1.0x")
        self.speed_label.grid(row=1, column=2, padx=8, pady=4)
        options_frame.columnconfigure(1, weight=1)

        hotkey_frame = ttk.LabelFrame(self.root, text="Tecla de inicio/paro")
        hotkey_frame.pack(fill="x", **padding)
        ttk.Label(hotkey_frame, text="Tecla actual:").grid(
            row=0, column=0, padx=8, pady=6, sticky="w"
        )
        ttk.Label(
            hotkey_frame, textvariable=self.hotkey_label_var, font=("Helvetica", 11, "bold")
        ).grid(row=0, column=1, padx=8, pady=6, sticky="w")
        self.change_hotkey_btn = ttk.Button(
            hotkey_frame, text="Cambiar tecla", command=self._capture_hotkey
        )
        self.change_hotkey_btn.grid(row=0, column=2, padx=8, pady=6)

        ttk.Label(
            self.root,
            text="La tecla inicia/detiene la grabación o la reproducción activa.",
            foreground="#555",
        ).pack(pady=(4, 0))

    def _on_speed_change(self, _value: str) -> None:
        self.speed_label.config(text=f"{self.speed_var.get():.2f}x")

    def _format_key(self, key: Key | KeyCode) -> str:
        if isinstance(key, Key):
            return key.name.upper()
        if isinstance(key, KeyCode) and key.char is not None:
            return key.char.upper()
        return str(key)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _update_count(self) -> None:
        self.event_count_var.set(f"Eventos: {len(self.events)}")

    def toggle_recording(self) -> None:
        if self.playing:
            return
        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        self.events = []
        self._update_count()
        self.recording = True
        self.record_start_time = time.time()
        self.record_btn.config(text="Detener grabación")
        self.play_btn.config(state="disabled")
        self._set_status("Grabando...")

        self.mouse_listener = mouse.Listener(
            on_move=self._on_move, on_click=self._on_click, on_scroll=self._on_scroll
        )
        self.mouse_listener.start()

    def _stop_recording(self) -> None:
        self.recording = False
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
            self.mouse_listener = None
        self.record_btn.config(text="Grabar")
        self.play_btn.config(state="normal")
        self._set_status(f"Grabación detenida ({len(self.events)} eventos)")
        self._update_count()

    def _on_move(self, x: int, y: int) -> None:
        if not self.recording:
            return
        self.events.append(
            {"type": "move", "t": time.time() - self.record_start_time, "x": x, "y": y}
        )
        self.root.after(0, self._update_count)

    def _on_click(self, x: int, y: int, button: Button, pressed: bool) -> None:
        if not self.recording:
            return
        self.events.append(
            {
                "type": "click",
                "t": time.time() - self.record_start_time,
                "x": x,
                "y": y,
                "button": button.name,
                "pressed": pressed,
            }
        )
        self.root.after(0, self._update_count)

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if not self.recording:
            return
        self.events.append(
            {
                "type": "scroll",
                "t": time.time() - self.record_start_time,
                "x": x,
                "y": y,
                "dx": dx,
                "dy": dy,
            }
        )
        self.root.after(0, self._update_count)

    def toggle_playback(self) -> None:
        if self.recording:
            return
        if self.playing:
            self._stop_playback()
        else:
            self._start_playback()

    def _start_playback(self) -> None:
        if not self.events:
            messagebox.showinfo("Sin grabación", "No hay eventos para reproducir.")
            return
        self.playing = True
        self.stop_playback_event.clear()
        self.play_btn.config(text="Detener reproducción")
        self.record_btn.config(state="disabled")
        self._set_status("Reproduciendo...")

        self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.playback_thread.start()

    def _stop_playback(self) -> None:
        self.stop_playback_event.set()
        self.playing = False
        self.play_btn.config(text="Reproducir")
        self.record_btn.config(state="normal")
        self._set_status("Reproducción detenida")

    def _playback_loop(self) -> None:
        try:
            speed = max(0.01, self.speed_var.get())
            while True:
                start = time.time()
                for event in self.events:
                    if self.stop_playback_event.is_set():
                        return
                    target = event["t"] / speed
                    while True:
                        if self.stop_playback_event.is_set():
                            return
                        remaining = target - (time.time() - start)
                        if remaining <= 0:
                            break
                        time.sleep(min(remaining, 0.02))
                    self._execute_event(event)
                if not self.loop_var.get():
                    break
        finally:
            self.root.after(0, self._on_playback_finished)

    def _execute_event(self, event: dict) -> None:
        kind = event["type"]
        if kind == "move":
            self.mouse_controller.position = (event["x"], event["y"])
        elif kind == "click":
            self.mouse_controller.position = (event["x"], event["y"])
            button = Button[event["button"]]
            if event["pressed"]:
                self.mouse_controller.press(button)
            else:
                self.mouse_controller.release(button)
        elif kind == "scroll":
            self.mouse_controller.position = (event["x"], event["y"])
            self.mouse_controller.scroll(event["dx"], event["dy"])

    def _on_playback_finished(self) -> None:
        self.playing = False
        self.play_btn.config(text="Reproducir")
        self.record_btn.config(state="normal")
        self._set_status("Reproducción finalizada")

    def clear_events(self) -> None:
        if self.recording or self.playing:
            return
        self.events = []
        self._update_count()
        self._set_status("Eventos limpiados")

    def save_events(self) -> None:
        if not self.events:
            messagebox.showinfo("Sin datos", "No hay eventos para guardar.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json"), ("Todos", "*.*")]
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.events, fh)
        self._set_status(f"Guardado en {path}")

    def load_events(self) -> None:
        if self.recording or self.playing:
            return
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                self.events = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Error", f"No se pudo cargar: {exc}")
            return
        self._update_count()
        self._set_status(f"Cargado: {path}")

    def _capture_hotkey(self) -> None:
        self.capture_next_key = True
        self._set_status("Presiona la nueva tecla...")
        self.change_hotkey_btn.config(state="disabled")

    def _start_hotkey_listener(self) -> None:
        self.hotkey_listener = keyboard.Listener(on_press=self._on_key_press)
        self.hotkey_listener.start()

    def _on_key_press(self, key: Key | KeyCode) -> None:
        if self.capture_next_key:
            self.hotkey = key
            self.capture_next_key = False
            self.root.after(0, self._finish_hotkey_capture)
            return
        if self._keys_equal(key, self.hotkey):
            self.root.after(0, self._handle_hotkey)

    def _finish_hotkey_capture(self) -> None:
        self.hotkey_label_var.set(self._format_key(self.hotkey))
        self.change_hotkey_btn.config(state="normal")
        self._set_status(f"Tecla asignada: {self._format_key(self.hotkey)}")

    def _keys_equal(self, a: Key | KeyCode, b: Key | KeyCode) -> bool:
        if isinstance(a, Key) and isinstance(b, Key):
            return a == b
        if isinstance(a, KeyCode) and isinstance(b, KeyCode):
            return a.char == b.char
        return False

    def _handle_hotkey(self) -> None:
        if self.playing:
            self._stop_playback()
        elif self.recording:
            self._stop_recording()
        else:
            if self.events:
                self._start_playback()
            else:
                self._start_recording()

    def _on_close(self) -> None:
        self.stop_playback_event.set()
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
        if self.hotkey_listener is not None:
            self.hotkey_listener.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    MouseRecorderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

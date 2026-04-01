"""
Side_A - Photo Organization GUI

A polished desktop interface for photographers. AI-powered photo sorting
into Lightroom-friendly metadata outputs (no file moving or renaming).
"""

import csv
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import customtkinter as ctk
from PIL import Image, ImageTk
from tkinter import Canvas, Label as TkLabel
from tkinter import ttk

# Add project root to path for PyInstaller / direct run
if getattr(sys, "frozen", False):
    _base = Path(sys.executable).parent
else:
    _base = Path(__file__).parent
sys.path.insert(0, str(_base))

from app import format_summary, run_processing
from vision_client import CREDENTIALS_ERROR_MESSAGE

# Icons (Unicode - work everywhere)
ICON_FOLDER = "📁"
ICON_LIGHTNING = "⚡"
ICON_CHECK = "✓"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_status_queue: queue.Queue = queue.Queue()
OUTPUTS_SUBFOLDER = "SideA_Metadata"

THUMB_SIZE = (160, 120)


def _get_app_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _find_background_path() -> Optional[Path]:
    if getattr(sys, "frozen", False):
        search_dirs = []
        if hasattr(sys, "_MEIPASS"):
            search_dirs.append(Path(sys._MEIPASS))
        search_dirs.append(Path(sys.executable).parent)
    else:
        base = Path(__file__).parent
        search_dirs = [base / "public", base]
    for search_dir in search_dirs:
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
            p = search_dir / f"background{ext}"
            if p.is_file():
                return p
    return None


def _queue_status(msg: str) -> None:
    _status_queue.put(msg)


def _queue_progress(current: int, total: int, image_path: Optional[str] = None, category: Optional[str] = None) -> None:
    _status_queue.put(("PROGRESS", current, total, image_path, category))


def _queue_result(success: bool, message: str, summary: Optional[Dict] = None) -> None:
    _status_queue.put(("RESULT", success, message, summary))


class SideAApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Side A Metadata Tagging Assistant")
        self.geometry("620x680")
        self.minsize(520, 600)

        self.photos_folder = ctk.StringVar(value="")
        self._output_folder_after_done: Optional[str] = None
        self._suggested_keywords_csv_after_done: Optional[str] = None
        self._bg_photo: Any = None
        self._bg_image_pil: Any = None
        self._thumb_photo: Any = None

        self.configure(fg_color="#1a1a2e")

        self._canvas = Canvas(self, highlightthickness=0, bg="#1a1a2e")
        self._canvas.pack(fill="both", expand=True)

        bg_path = _find_background_path()
        if bg_path:
            try:
                self._bg_image_pil = Image.open(str(bg_path)).convert("RGB")
                self.after(100, self._update_background_image)
                self.bind("<Configure>", self._on_resize)
            except Exception:
                self._bg_image_pil = None

        self._build_ui()
        self._start_queue_poll()

    def _on_resize(self, event: Any) -> None:
        if self._bg_image_pil and event.widget == self:
            self._update_background_image()

    def _update_background_image(self) -> None:
        if not self._bg_image_pil:
            return
        try:
            w = self.winfo_width()
            h = self.winfo_height()
            if w < 10 or h < 10:
                return
            resized = self._bg_image_pil.copy().resize((w, h), Image.Resampling.LANCZOS)
            self._bg_photo = ImageTk.PhotoImage(resized)
            self._canvas.delete("all")
            self._canvas.create_image(0, 0, anchor="nw", image=self._bg_photo)
        except Exception:
            pass

    def _build_ui(self) -> None:
        # Semi-transparent panel - dark overlay for readability
        self._main = ctk.CTkFrame(
            self,
            fg_color=("#2d2d3a", "#1e1e28"),
            corner_radius=16,
            border_width=0,
        )
        self._main.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.88, relheight=0.9)

        inner = ctk.CTkFrame(self._main, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=32, pady=28)

        # Title - large and centered
        title_frame = ctk.CTkFrame(inner, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 4))
        title = ctk.CTkLabel(
            title_frame,
            text="Side A Metadata Tagging Assistant",
            font=ctk.CTkFont(size=28, weight="bold"),
        )
        title.pack(anchor="center")
        subtitle = ctk.CTkLabel(
            title_frame,
            text="Lightroom-safe metadata + keyword suggestions",
            font=ctk.CTkFont(size=14),
            text_color=("gray60", "gray70"),
        )
        subtitle.pack(anchor="center", pady=(2, 0))

        safety = ctk.CTkLabel(
            title_frame,
            text="This tool does not move or rename your original files.",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#93c5fd", "#bfdbfe"),
        )
        safety.pack(anchor="center", pady=(10, 0))

        # Folder selection - centered
        folder_frame = ctk.CTkFrame(inner, fg_color="transparent")
        folder_frame.pack(fill="x", pady=(24, 12))

        folder_row = ctk.CTkFrame(folder_frame, fg_color="transparent")
        folder_row.pack(anchor="center")
        self._folder_entry = ctk.CTkEntry(
            folder_row,
            textvariable=self.photos_folder,
            placeholder_text="Choose folder with your photos...",
            width=340,
            height=40,
            font=ctk.CTkFont(size=13),
        )
        self._folder_entry.pack(side="left", padx=(0, 10))
        self._browse_btn = ctk.CTkButton(
            folder_row,
            text=f" {ICON_FOLDER}  Browse",
            width=120,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._select_folder,
        )
        self._browse_btn.pack(side="left")

        # Start Processing - large button
        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(pady=(16, 20))
        self._start_btn = ctk.CTkButton(
            btn_frame,
            text=f" {ICON_LIGHTNING}  Start Processing",
            font=ctk.CTkFont(size=18, weight="bold"),
            height=52,
            width=280,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            corner_radius=12,
            command=self._on_start,
        )
        self._start_btn.pack(anchor="center")

        # Progress area - live counter, thumbnail, detected
        self._progress_frame = ctk.CTkFrame(inner, fg_color="transparent")
        self._progress_frame.pack(fill="x", pady=(8, 12))

        self._counter_label = ctk.CTkLabel(
            self._progress_frame,
            text="",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=("gray80", "gray90"),
        )
        self._counter_label.pack(anchor="center", pady=(0, 8))

        self._thumb_frame = ctk.CTkFrame(self._progress_frame, fg_color=("gray30", "gray20"), corner_radius=8, width=170, height=130)
        self._thumb_frame.pack(anchor="center", pady=(0, 8))
        self._thumb_frame.pack_propagate(False)
        self._thumb_label = TkLabel(
            self._thumb_frame,
            text="",
            bg="#2d2d3a",
            fg="gray",
            font=("Segoe UI", 10),
        )
        self._thumb_label.place(relx=0.5, rely=0.5, anchor="center")

        self._detected_label = ctk.CTkLabel(
            self._progress_frame,
            text="",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#3b82f6", "#60a5fa"),
        )
        self._detected_label.pack(anchor="center", pady=(4, 0))

        # Progress bar
        self._progress = ctk.CTkProgressBar(inner, height=10, corner_radius=5)
        self._progress.pack(fill="x", pady=(12, 16))
        self._progress.set(0)

        # Status / Summary area
        self._status_frame = ctk.CTkFrame(inner, fg_color="transparent")
        self._status_frame.pack(fill="both", expand=True, pady=(0, 12))

        ctk.CTkLabel(self._status_frame, text="Status", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(0, 4))
        self._status_text = ctk.CTkTextbox(
            self._status_frame,
            height=100,
            font=ctk.CTkFont(size=12),
            state="disabled",
            fg_color=("gray20", "gray15"),
        )
        self._status_text.pack(fill="x", pady=(0, 12))

        # Open Results Folder - hidden until done
        self._open_btn = ctk.CTkButton(
            inner,
            text=f" {ICON_CHECK}  Open Results Folder",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=44,
            fg_color="#059669",
            hover_color="#047857",
            corner_radius=10,
            command=self._open_output_folder,
        )
        self._open_btn.pack(fill="x")
        self._open_btn.pack_forget()

        # Review button - hidden until done
        self._review_btn = ctk.CTkButton(
            inner,
            text="Review & Edit Suggested Keywords",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            corner_radius=10,
            command=self._open_review_window,
        )
        self._review_btn.pack(fill="x", pady=(10, 0))
        self._review_btn.pack_forget()

    def _select_folder(self) -> None:
        path = ctk.filedialog.askdirectory(title="Select folder with photos")
        if path:
            self.photos_folder.set(path)

    def _set_processing_state(self, processing: bool) -> None:
        state = "disabled" if processing else "normal"
        self._start_btn.configure(state=state)
        self._browse_btn.configure(state=state)
        self._folder_entry.configure(state=state)

    def _show_thumbnail(self, image_path: Optional[str], category: Optional[str]) -> None:
        self._thumb_label.configure(image="", text="")
        self._thumb_photo = None
        if image_path and os.path.isfile(image_path):
            try:
                img = Image.open(image_path).convert("RGB")
                img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
                self._thumb_photo = ImageTk.PhotoImage(img)
                self._thumb_label.configure(image=self._thumb_photo, text="")
            except Exception:
                self._thumb_label.configure(text="[Preview]")
        else:
            self._thumb_label.configure(text="[Preview]")

        if category:
            self._detected_label.configure(text=f"Detected: {category}")
        else:
            self._detected_label.configure(text="")

    def _append_status(self, msg: str) -> None:
        self._status_text.configure(state="normal")
        self._status_text.insert("end", msg + "\n")
        self._status_text.see("end")
        self._status_text.configure(state="disabled")

    def _start_queue_poll(self) -> None:
        try:
            while True:
                item = _status_queue.get_nowait()
                if isinstance(item, tuple):
                    if item[0] == "RESULT":
                        _, success, message, summary = item
                        self._on_processing_done(success, message, summary)
                    elif item[0] == "PROGRESS":
                        _, current, total, image_path, category = item
                        if total > 0:
                            self._progress.set(current / total)
                        self._counter_label.configure(text=f"Analyzing image {current} of {total}")
                        self._show_thumbnail(image_path, category)
                else:
                    self._append_status(str(item))
        except queue.Empty:
            pass
        self.after(100, self._start_queue_poll)

    def _on_start(self) -> None:
        folder = self.photos_folder.get().strip()
        if not folder:
            self._append_status("Please select a folder with your photos.")
            return
        if not os.path.isdir(folder):
            self._append_status("The selected folder does not exist.")
            return

        output_dir = os.path.join(folder, OUTPUTS_SUBFOLDER)

        self._set_processing_state(True)
        self._start_btn.configure(text=" Processing...")
        self._progress.set(0)
        self._counter_label.configure(text="")
        self._detected_label.configure(text="")
        self._show_thumbnail(None, None)
        self._status_text.configure(state="normal")
        self._status_text.delete("1.0", "end")
        self._status_text.configure(state="disabled")
        self._open_btn.pack_forget()
        self._review_btn.pack_forget()

        def worker() -> None:
            try:
                success, message, summary = run_processing(
                    folder,
                    output_dir,
                    status_callback=_queue_status,
                    progress_callback=_queue_progress,
                    keep_previews=False,
                )
                _queue_result(success, message, summary)
            except Exception as e:
                err = str(e).lower()
                if any(p in err for p in ("credentials", "default credentials", "authentication", "your default credentials were not found")):
                    _queue_result(False, CREDENTIALS_ERROR_MESSAGE, None)
                else:
                    _queue_result(False, str(e), None)

        threading.Thread(target=worker, daemon=True).start()

    def _on_processing_done(
        self,
        success: bool,
        message: str,
        summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._set_processing_state(False)
        self._start_btn.configure(text=f" {ICON_LIGHTNING}  Start Processing")
        self._progress.set(1.0)

        if success and summary:
            self._counter_label.configure(text="Complete!")
            self._show_thumbnail(None, None)
            self._append_status("")
            self._append_status("─── Summary ───")
            self._append_status("")
            self._append_status(format_summary(summary))
            folder = self.photos_folder.get().strip()
            self._output_folder_after_done = os.path.join(folder, OUTPUTS_SUBFOLDER)
            outputs = summary.get("outputs") or {}
            self._suggested_keywords_csv_after_done = outputs.get("suggested_keywords_csv")
            if os.path.isdir(self._output_folder_after_done):
                self._open_btn.pack(fill="x", pady=(8, 0))
                self._review_btn.pack(fill="x", pady=(10, 0))
        elif success:
            self._counter_label.configure(text="Complete!")
            folder = self.photos_folder.get().strip()
            self._output_folder_after_done = os.path.join(folder, OUTPUTS_SUBFOLDER)
            if os.path.isdir(self._output_folder_after_done):
                self._open_btn.pack(fill="x", pady=(8, 0))
                self._review_btn.pack(fill="x", pady=(10, 0))
        else:
            self._counter_label.configure(text="")
            self._append_status("")
            self._append_status("─── Error ───")
            self._append_status("")
            for line in message.split("\n"):
                self._append_status(line)

    def _open_output_folder(self) -> None:
        folder = self._output_folder_after_done or ""
        if folder and os.path.isdir(folder):
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.run(["open", folder], check=False)
            else:
                subprocess.run(["xdg-open", folder], check=False)

    def _open_review_window(self) -> None:
        csv_path = self._suggested_keywords_csv_after_done or ""
        if not csv_path or not os.path.isfile(csv_path):
            self._append_status("Could not find suggested_keywords.csv to review.")
            return

        win = ctk.CTkToplevel(self)
        win.title("Review Suggested Keywords")
        win.geometry("920x520")

        container = ctk.CTkFrame(win, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16, pady=16)

        header = ctk.CTkLabel(
            container,
            text="Edit keywords and categories, then Save.",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        header.pack(anchor="w", pady=(0, 10))

        columns = ("filename", "original_path", "suggested_keywords", "primary_category", "notes")
        tree = ttk.Treeview(container, columns=columns, show="headings", height=14)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=160 if col != "original_path" else 280, stretch=True)

        yscroll = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=yscroll.set)
        tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="left", fill="y")

        rows: list[dict[str, str]] = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                row = {c: (r.get(c) or "") for c in columns}
                rows.append(row)
                tree.insert("", "end", values=tuple(row[c] for c in columns))

        editor = ctk.CTkFrame(container, fg_color="transparent")
        editor.pack(side="left", fill="y", padx=(12, 0))

        selected_idx: dict[str, Optional[int]] = {"i": None}

        kw_var = ctk.StringVar(value="")
        cat_var = ctk.StringVar(value="")
        notes_var = ctk.StringVar(value="")

        ctk.CTkLabel(editor, text="Suggested keywords", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        kw_entry = ctk.CTkTextbox(editor, height=160, width=260)
        kw_entry.pack(fill="x", pady=(4, 10))

        ctk.CTkLabel(editor, text="Primary category", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        cat_entry = ctk.CTkEntry(editor, textvariable=cat_var, width=260)
        cat_entry.pack(fill="x", pady=(4, 10))

        ctk.CTkLabel(editor, text="Notes", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        notes_entry = ctk.CTkEntry(editor, textvariable=notes_var, width=260)
        notes_entry.pack(fill="x", pady=(4, 10))

        def load_selection() -> None:
            sel = tree.selection()
            if not sel:
                return
            item_id = sel[0]
            values = tree.item(item_id, "values")
            if not values:
                return
            # Find row index by filename+original_path match
            fn, op = values[0], values[1]
            idx = next((j for j, r in enumerate(rows) if r["filename"] == fn and r["original_path"] == op), None)
            selected_idx["i"] = idx
            if idx is None:
                return
            kw_entry.delete("1.0", "end")
            kw_entry.insert("1.0", rows[idx]["suggested_keywords"])
            cat_var.set(rows[idx]["primary_category"])
            notes_var.set(rows[idx]["notes"])

        def apply_edits_to_selected() -> None:
            idx = selected_idx["i"]
            sel = tree.selection()
            if idx is None or not sel:
                return
            rows[idx]["suggested_keywords"] = kw_entry.get("1.0", "end").strip()
            rows[idx]["primary_category"] = (cat_var.get() or "").strip()
            rows[idx]["notes"] = (notes_var.get() or "").strip()
            item_id = sel[0]
            tree.item(
                item_id,
                values=(
                    rows[idx]["filename"],
                    rows[idx]["original_path"],
                    rows[idx]["suggested_keywords"],
                    rows[idx]["primary_category"],
                    rows[idx]["notes"],
                ),
            )

        def save_csv() -> None:
            apply_edits_to_selected()
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(columns))
                writer.writeheader()
                for r in rows:
                    writer.writerow(r)
            self._append_status(f"Saved edits to: {csv_path}")

        tree.bind("<<TreeviewSelect>>", lambda _e: load_selection())

        ctk.CTkButton(editor, text="Apply edits to selected row", command=apply_edits_to_selected).pack(fill="x", pady=(6, 6))
        ctk.CTkButton(editor, text="Save CSV", fg_color="#059669", hover_color="#047857", command=save_csv).pack(fill="x")


def main() -> None:
    app = SideAApp()
    app.mainloop()


if __name__ == "__main__":
    main()

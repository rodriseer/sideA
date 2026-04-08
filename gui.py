"""
Desktop GUI for photographer metadata workflow (Lightroom-safe).

User-facing strings live in branding.py; credentials path in user data config.json.
"""

from __future__ import annotations

import csv
import os
import queue
import subprocess
import sys
import threading
import webbrowser
import tkinter as tk
from pathlib import Path
from typing import Any, Dict, Optional

import customtkinter as ctk
from PIL import Image, ImageTk
from tkinter import Canvas, Label as TkLabel, messagebox, ttk

from bundle_paths import get_resource_search_dirs, get_runtime_base_dir

# Add project root to path for PyInstaller / direct run
_base = get_runtime_base_dir() if getattr(sys, "frozen", False) else Path(__file__).parent
sys.path.insert(0, str(_base))

import branding
from app import format_summary, run_processing
from organizer import normalize_original_path_for_sidecar, rewrite_xmp_sidecar_if_exists, xmp_sidecar_path_for_image
from user_settings import (
    apply_saved_credentials_to_environment,
    get_config_path,
    get_configured_credentials_path_raw,
    get_saved_credentials_path,
    set_saved_credentials_path,
)
from vision_client import (
    CREDENTIALS_ERROR_MESSAGE,
    check_vision_credentials,
    get_vision_client,
    validate_service_account_json_file,
)

# Icons (Unicode - work everywhere)
ICON_FOLDER = "📁"
ICON_LIGHTNING = "⚡"
ICON_CHECK = "✓"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_status_queue: queue.Queue = queue.Queue()

THUMB_SIZE = (160, 120)


def _get_app_base() -> Path:
    return get_runtime_base_dir() if getattr(sys, "frozen", False) else Path(__file__).parent


def _find_background_path() -> Optional[Path]:
    for search_dir in get_resource_search_dirs():
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


def open_setup_guide_window(parent: ctk.CTk, on_saved: Optional[Any] = None) -> None:
    """Beginner-friendly onboarding: steps, file pick, test, auto-save on success."""
    win = ctk.CTkToplevel(parent)
    win.title(branding.SETUP_GUIDE_TITLE)
    win.geometry("600x820")
    win.minsize(520, 680)
    win.transient(parent)
    win.grab_set()
    win.configure(fg_color=("#f4f4f5", "#1a1a24"))

    root = ctk.CTkFrame(win, fg_color=("white", "#22222e"), corner_radius=0)
    root.pack(fill="both", expand=True)

    raw_saved = get_configured_credentials_path_raw()
    selected_path = ctk.StringVar(value=get_saved_credentials_path() or raw_saved)
    test_detail_var = ctk.StringVar(value="")

    connection_status = ctk.StringVar(value=branding.CREDENTIALS_STATUS_NOT_CONFIGURED)
    connection_color: dict[str, tuple[str, str]] = {"ok": ("#15803d", "#4ade80"), "bad": ("#c2410c", "#fdba74")}

    def update_path_display() -> None:
        p = selected_path.get().strip()
        if p and os.path.isfile(p):
            short = os.path.basename(p)
            path_display.configure(text=short)
        else:
            path_display.configure(text=branding.SETUP_GUIDE_PATH_HINT)

    def refresh_connection_badge() -> None:
        apply_saved_credentials_to_environment()
        ok, _, _ = check_vision_credentials()
        if ok:
            connection_status.set(branding.CREDENTIALS_STATUS_CONFIGURED)
            badge.configure(text_color=connection_color["ok"])
        else:
            connection_status.set(branding.CREDENTIALS_STATUS_NOT_CONFIGURED)
            badge.configure(text_color=connection_color["bad"])

    # --- Header ---
    header = ctk.CTkFrame(root, fg_color="transparent")
    header.pack(fill="x", padx=32, pady=(28, 16))

    ctk.CTkLabel(
        header,
        text=branding.SETUP_GUIDE_TITLE,
        font=ctk.CTkFont(size=26, weight="bold"),
    ).pack(anchor="w")
    ctk.CTkLabel(
        header,
        text=branding.SETUP_GUIDE_SUBTITLE,
        font=ctk.CTkFont(size=16),
        text_color=("gray45", "gray65"),
    ).pack(anchor="w", pady=(6, 14))

    badge_row = ctk.CTkFrame(header, fg_color=("gray92", "#2d2d3a"), corner_radius=14)
    badge_row.pack(fill="x", pady=(0, 4))
    inner_badge = ctk.CTkFrame(badge_row, fg_color="transparent")
    inner_badge.pack(fill="x", padx=18, pady=14)
    badge = ctk.CTkLabel(
        inner_badge,
        textvariable=connection_status,
        font=ctk.CTkFont(size=17, weight="bold"),
        anchor="w",
    )
    badge.pack(anchor="w")

    # --- Scrollable steps (packed after footer so bottom actions stay visible) ---
    scroll = ctk.CTkScrollableFrame(root, fg_color="transparent")

    steps = [
        branding.SETUP_GUIDE_STEP_1,
        branding.SETUP_GUIDE_STEP_2,
        branding.SETUP_GUIDE_STEP_3,
        branding.SETUP_GUIDE_STEP_4,
        branding.SETUP_GUIDE_STEP_5,
        branding.SETUP_GUIDE_STEP_6,
    ]
    for i, body in enumerate(steps, start=1):
        row = ctk.CTkFrame(scroll, fg_color="transparent")
        row.pack(fill="x", pady=(0, 18))
        ctk.CTkLabel(
            row,
            text=f"{i}.",
            font=ctk.CTkFont(size=17, weight="bold"),
            width=28,
            anchor="nw",
        ).pack(side="left", anchor="nw", pady=(2, 0))
        ctk.CTkLabel(
            row,
            text=body,
            font=ctk.CTkFont(size=16),
            text_color=("gray20", "gray85"),
            wraplength=480,
            justify="left",
            anchor="w",
        ).pack(side="left", fill="x", expand=True, pady=(0, 0))

        if i == 1:
            link = ctk.CTkLabel(
                scroll,
                text=branding.SETUP_GUIDE_LINK_TEXT + "  →",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=("#2563eb", "#60a5fa"),
                cursor="hand2",
            )
            link.pack(anchor="w", padx=(36, 0), pady=(0, 18))

            def _open_cloud(_e: Any = None) -> None:
                webbrowser.open(branding.SETUP_GUIDE_CLOUD_URL)

            link.bind("<Button-1>", _open_cloud)

    ctk.CTkLabel(
        scroll,
        text=branding.SETUP_GUIDE_PRIVACY_WARNING,
        font=ctk.CTkFont(size=13),
        text_color=("#b45309", "#fbbf24"),
        wraplength=500,
        justify="left",
    ).pack(anchor="w", pady=(8, 4))

    ctk.CTkLabel(
        scroll,
        text=f"{branding.CREDENTIALS_CONFIG_HINT}\n{get_config_path()}",
        font=ctk.CTkFont(size=12),
        text_color=("gray50", "gray55"),
        wraplength=500,
        justify="left",
    ).pack(anchor="w", pady=(16, 8))

    # --- Footer actions ---
    footer = ctk.CTkFrame(root, fg_color=("gray95", "#1e1e28"), corner_radius=0)
    foot_inner = ctk.CTkFrame(footer, fg_color="transparent")
    foot_inner.pack(fill="x", padx=32, pady=(24, 28))

    path_display = ctk.CTkLabel(
        foot_inner,
        text="",
        font=ctk.CTkFont(size=14),
        text_color=("gray40", "gray60"),
    )
    path_display.pack(anchor="w", pady=(0, 12))
    update_path_display()

    def browse() -> None:
        path = ctk.filedialog.askopenfilename(
            title=branding.CREDENTIALS_FILE_DIALOG_TITLE,
            filetypes=[("JSON credentials", "*.json"), ("All files", "*.*")],
            parent=win,
        )
        if path:
            selected_path.set(path)
            update_path_display()
            test_detail_var.set(branding.SETUP_GUIDE_TEST_TO_FINISH)

    ctk.CTkButton(
        foot_inner,
        text=branding.BTN_SELECT_CREDENTIALS_JSON,
        font=ctk.CTkFont(size=18, weight="bold"),
        height=56,
        corner_radius=12,
        fg_color="#2563eb",
        hover_color="#1d4ed8",
        command=browse,
    ).pack(fill="x", pady=(0, 12))

    result_q: queue.Queue = queue.Queue()

    def do_test_connection() -> None:
        path = selected_path.get().strip()
        if not path or not os.path.isfile(path):
            test_detail_var.set(branding.CREDENTIALS_ERROR_NO_FILE)
            return
        ok_shape, shape_msg = validate_service_account_json_file(path)
        if not ok_shape:
            test_detail_var.set(shape_msg)
            return

        def worker() -> None:
            old = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
            abs_path = os.path.abspath(path)
            try:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_path
                ok, msg, _ = check_vision_credentials()
                if not ok:
                    result_q.put((False, msg or branding.CREDENTIALS_FAILURE))
                    return
                try:
                    client = get_vision_client()
                    del client
                except Exception as exc:
                    result_q.put((False, str(exc)))
                    return
                result_q.put((True, abs_path))
            finally:
                if old:
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = old
                else:
                    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

        threading.Thread(target=worker, daemon=True).start()

        def poll() -> None:
            try:
                ok, payload = result_q.get_nowait()
                if ok:
                    abs_path = str(payload)
                    set_saved_credentials_path(abs_path)
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_path
                    test_detail_var.set(branding.CREDENTIALS_SUCCESS)
                    refresh_connection_badge()
                    if on_saved:
                        on_saved()
                else:
                    apply_saved_credentials_to_environment()
                    test_detail_var.set((str(payload) or branding.CREDENTIALS_FAILURE)[:400])
                    refresh_connection_badge()
            except queue.Empty:
                win.after(150, poll)

        test_detail_var.set(branding.CREDENTIALS_TESTING)
        poll()

    ctk.CTkButton(
        foot_inner,
        text=branding.BTN_TEST_CONNECTION,
        font=ctk.CTkFont(size=16, weight="bold"),
        height=46,
        corner_radius=10,
        fg_color=("gray75", "#374151"),
        hover_color=("gray65", "#4b5563"),
        command=do_test_connection,
    ).pack(fill="x", pady=(0, 8))

    ctk.CTkLabel(
        foot_inner,
        textvariable=test_detail_var,
        font=ctk.CTkFont(size=14),
        text_color=("gray35", "gray60"),
        wraplength=520,
        justify="left",
    ).pack(anchor="w", pady=(4, 0))

    footer.pack(fill="x", side="bottom")
    scroll.pack(fill="both", expand=True, padx=32, pady=(0, 8))

    refresh_connection_badge()
    if not get_saved_credentials_path() and selected_path.get().strip():
        test_detail_var.set(branding.SETUP_GUIDE_TEST_TO_FINISH)


class PhotoMetadataApp(ctk.CTk):
    """Main window; all product copy comes from branding.py."""

    def __init__(self) -> None:
        super().__init__()

        self.title(branding.WINDOW_TITLE)
        self.geometry("640x720")
        self.minsize(540, 620)

        self.photos_folder = ctk.StringVar(value="")
        self._output_folder_after_done: Optional[str] = None
        self._suggested_keywords_csv_after_done: Optional[str] = None
        self._bg_photo: Any = None
        self._bg_image_pil: Any = None
        self._thumb_photo: Any = None
        self._is_processing = False
        self._first_run_credentials_prompt_shown = False

        self.configure(fg_color="#1a1a2e")

        apply_saved_credentials_to_environment()

        menubar = tk.Menu(self)
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(
            label=branding.MENU_SETTINGS_CREDENTIALS,
            command=lambda: open_setup_guide_window(self, self._refresh_credentials_status),
        )
        menubar.add_cascade(label=branding.MENU_SETTINGS, menu=settings_menu)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label=branding.MENU_HELP_ABOUT, command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.configure(menu=menubar)

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
        self._refresh_credentials_status()
        self._start_queue_poll()
        self.after(450, self._maybe_show_first_run_credentials_prompt)

    def _show_about(self) -> None:
        messagebox.showinfo(f"About {branding.APP_NAME}", branding.ABOUT_BLURB)

    def _sync_start_button_for_credentials(self) -> None:
        """Enable Start only when Vision credentials are configured and validated."""
        if self._is_processing:
            return
        ok, _, _ = check_vision_credentials()
        self._start_btn.configure(state="normal" if ok else "disabled")

    def _refresh_credentials_status(self) -> None:
        apply_saved_credentials_to_environment()
        ok, _, _ = check_vision_credentials()
        if ok:
            self._cred_hint.configure(text="", text_color=("gray60", "gray65"))
            self._cred_status.configure(
                text=branding.CREDENTIALS_STATUS_CONFIGURED,
                text_color=("#22c55e", "#4ade80"),
            )
        else:
            self._cred_hint.configure(
                text=branding.MSG_VISION_CREDENTIALS_REQUIRED,
                text_color=("#f97316", "#fdba74"),
            )
            self._cred_status.configure(
                text=branding.CREDENTIALS_STATUS_NOT_CONFIGURED,
                text_color=("gray65", "gray70"),
            )
        self._sync_start_button_for_credentials()

    def _maybe_show_first_run_credentials_prompt(self) -> None:
        if self._first_run_credentials_prompt_shown:
            return
        ok, _, _ = check_vision_credentials()
        if ok:
            return
        self._first_run_credentials_prompt_shown = True
        self._show_first_run_credentials_dialog()

    def _show_first_run_credentials_dialog(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title(branding.FIRST_RUN_TITLE)
        win.geometry("460x300")
        win.minsize(420, 260)
        win.transient(self)
        win.grab_set()
        win.focus_force()

        frame = ctk.CTkFrame(win, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(
            frame,
            text=branding.FIRST_RUN_BODY,
            font=ctk.CTkFont(size=13),
            text_color=("gray75", "gray80"),
            wraplength=400,
            justify="left",
        ).pack(anchor="w", pady=(0, 18))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", pady=(8, 0))

        def open_setup() -> None:
            win.destroy()
            open_setup_guide_window(self, self._refresh_credentials_status)

        def close_later() -> None:
            win.destroy()

        ctk.CTkButton(
            row,
            text=branding.FIRST_RUN_BTN_SETUP,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=36,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=open_setup,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            row,
            text=branding.FIRST_RUN_BTN_LATER,
            font=ctk.CTkFont(size=14),
            height=36,
            fg_color=("gray50", "gray40"),
            hover_color=("gray40", "gray35"),
            command=close_later,
        ).pack(side="left")

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
        self._main = ctk.CTkFrame(
            self,
            fg_color=("#2d2d3a", "#1e1e28"),
            corner_radius=16,
            border_width=0,
        )
        self._main.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.9, relheight=0.92)

        inner = ctk.CTkFrame(self._main, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=28, pady=24)

        cred_block = ctk.CTkFrame(inner, fg_color="transparent")
        cred_block.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            cred_block,
            text=branding.LABEL_VISION_SETUP,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("gray85", "gray90"),
        ).pack(anchor="w")
        self._cred_hint = ctk.CTkLabel(
            cred_block,
            text="",
            font=ctk.CTkFont(size=12),
            wraplength=480,
            justify="left",
        )
        self._cred_hint.pack(anchor="w", pady=(4, 8))
        ctk.CTkButton(
            cred_block,
            text=branding.BTN_SETUP_GUIDE,
            font=ctk.CTkFont(size=15, weight="bold"),
            height=42,
            corner_radius=10,
            fg_color=("#4f46e5", "#4338ca"),
            hover_color=("#4338ca", "#3730a3"),
            command=lambda: open_setup_guide_window(self, self._refresh_credentials_status),
        ).pack(fill="x", pady=(0, 10))
        cred_row = ctk.CTkFrame(cred_block, fg_color="transparent")
        cred_row.pack(fill="x", pady=(0, 0))
        self._cred_status = ctk.CTkLabel(
            cred_row,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self._cred_status.pack(side="left")
        ctk.CTkButton(
            cred_row,
            text=branding.BTN_SELECT_CREDENTIALS_JSON,
            width=220,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: open_setup_guide_window(self, self._refresh_credentials_status),
        ).pack(side="right")

        title_frame = ctk.CTkFrame(inner, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            title_frame,
            text=branding.APP_NAME,
            font=ctk.CTkFont(size=26, weight="bold"),
        ).pack(anchor="center")
        ctk.CTkLabel(
            title_frame,
            text=branding.APP_SUBTITLE,
            font=ctk.CTkFont(size=14),
            text_color=("gray60", "gray70"),
        ).pack(anchor="center", pady=(4, 0))
        ctk.CTkLabel(
            title_frame,
            text=branding.APP_DESCRIPTION,
            font=ctk.CTkFont(size=12),
            text_color=("gray65", "gray75"),
            wraplength=520,
            justify="center",
        ).pack(anchor="center", pady=(10, 0))
        ctk.CTkLabel(
            title_frame,
            text=branding.APP_SAFETY_NOTE,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#93c5fd", "#bfdbfe"),
            wraplength=520,
            justify="center",
        ).pack(anchor="center", pady=(10, 0))
        ctk.CTkLabel(
            title_frame,
            text=branding.APP_TRUST_NOTE,
            font=ctk.CTkFont(size=11),
            text_color=("gray55", "gray65"),
            wraplength=520,
            justify="center",
        ).pack(anchor="center", pady=(6, 0))

        folder_frame = ctk.CTkFrame(inner, fg_color="transparent")
        folder_frame.pack(fill="x", pady=(20, 12))

        folder_row = ctk.CTkFrame(folder_frame, fg_color="transparent")
        folder_row.pack(anchor="center")
        self._folder_entry = ctk.CTkEntry(
            folder_row,
            textvariable=self.photos_folder,
            placeholder_text=branding.PLACEHOLDER_PHOTOS_FOLDER,
            width=360,
            height=40,
            font=ctk.CTkFont(size=13),
        )
        self._folder_entry.pack(side="left", padx=(0, 10))
        self._browse_btn = ctk.CTkButton(
            folder_row,
            text=f" {ICON_FOLDER}  {branding.BTN_BROWSE_FOLDER}",
            width=120,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._select_folder,
        )
        self._browse_btn.pack(side="left")

        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(pady=(14, 18))
        self._start_btn = ctk.CTkButton(
            btn_frame,
            text=f" {ICON_LIGHTNING}  {branding.BTN_START_ANALYSIS}",
            font=ctk.CTkFont(size=18, weight="bold"),
            height=52,
            width=300,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            corner_radius=12,
            command=self._on_start,
        )
        self._start_btn.pack(anchor="center")

        self._progress_frame = ctk.CTkFrame(inner, fg_color="transparent")
        self._progress_frame.pack(fill="x", pady=(6, 10))

        self._counter_label = ctk.CTkLabel(
            self._progress_frame,
            text="",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=("gray80", "gray90"),
        )
        self._counter_label.pack(anchor="center", pady=(0, 8))

        self._thumb_frame = ctk.CTkFrame(
            self._progress_frame, fg_color=("gray30", "gray20"), corner_radius=8, width=170, height=130
        )
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

        self._progress = ctk.CTkProgressBar(inner, height=10, corner_radius=5)
        self._progress.pack(fill="x", pady=(10, 14))
        self._progress.set(0)

        self._status_frame = ctk.CTkFrame(inner, fg_color="transparent")
        self._status_frame.pack(fill="both", expand=True, pady=(0, 10))

        ctk.CTkLabel(self._status_frame, text=branding.LABEL_STATUS, font=ctk.CTkFont(size=12, weight="bold")).pack(
            anchor="w", pady=(0, 4)
        )
        self._status_text = ctk.CTkTextbox(
            self._status_frame,
            height=110,
            font=ctk.CTkFont(size=12),
            state="disabled",
            fg_color=("gray20", "gray15"),
        )
        self._status_text.pack(fill="x", pady=(0, 10))

        self._open_btn = ctk.CTkButton(
            inner,
            text=f" {ICON_CHECK}  {branding.BTN_OPEN_RESULTS}",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=44,
            fg_color="#059669",
            hover_color="#047857",
            corner_radius=10,
            command=self._open_output_folder,
        )
        self._open_btn.pack(fill="x")
        self._open_btn.pack_forget()

        self._review_btn = ctk.CTkButton(
            inner,
            text=branding.BTN_REVIEW_KEYWORDS,
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
        path = ctk.filedialog.askdirectory(title="Select folder with photos or RAW files")
        if path:
            self.photos_folder.set(path)

    def _set_processing_state(self, processing: bool) -> None:
        self._is_processing = processing
        browse_state = "disabled" if processing else "normal"
        self._browse_btn.configure(state=browse_state)
        self._folder_entry.configure(state=browse_state)
        if processing:
            self._start_btn.configure(state="disabled")
        else:
            self._sync_start_button_for_credentials()

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

        apply_saved_credentials_to_environment()
        ok, cred_msg, _ = check_vision_credentials()
        if not ok:
            self._append_status(cred_msg or branding.CREDENTIALS_MISSING_GUI)
            alert_body = branding.CREDENTIALS_MISSING_GUI
            messagebox.showwarning(branding.LABEL_VISION_SETUP, alert_body)
            self._refresh_credentials_status()
            return

        output_dir = os.path.join(folder, branding.OUTPUTS_SUBFOLDER)

        self._set_processing_state(True)
        self._start_btn.configure(text=" Working…")
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
                if any(
                    p in err
                    for p in (
                        "credentials",
                        "default credentials",
                        "authentication",
                        "your default credentials were not found",
                    )
                ):
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
        self._start_btn.configure(text=f" {ICON_LIGHTNING}  {branding.BTN_START_ANALYSIS}")
        self._progress.set(1.0)
        self._refresh_credentials_status()

        if success and summary:
            self._counter_label.configure(text="Complete!")
            self._show_thumbnail(None, None)
            self._append_status("")
            self._append_status("─── Summary ───")
            self._append_status("")
            self._append_status(format_summary(summary))
            folder = self.photos_folder.get().strip()
            self._output_folder_after_done = os.path.join(folder, branding.OUTPUTS_SUBFOLDER)
            outputs = summary.get("outputs") or {}
            self._suggested_keywords_csv_after_done = outputs.get("suggested_keywords_csv")
            if os.path.isdir(self._output_folder_after_done):
                self._open_btn.pack(fill="x", pady=(8, 0))
                self._review_btn.pack(fill="x", pady=(10, 0))
        elif success:
            self._counter_label.configure(text="Complete!")
            folder = self.photos_folder.get().strip()
            self._output_folder_after_done = os.path.join(folder, branding.OUTPUTS_SUBFOLDER)
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
        win.title(f"{branding.APP_NAME} — {branding.BTN_REVIEW_KEYWORDS}")
        win.geometry("920x540")

        container = ctk.CTkFrame(win, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            container,
            text=branding.REVIEW_INTRO_XMP,
            font=ctk.CTkFont(size=13, weight="bold"),
            wraplength=860,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

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

        cat_var = ctk.StringVar(value="")
        notes_var = ctk.StringVar(value="")

        ctk.CTkLabel(editor, text="Suggested keywords", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        kw_entry = ctk.CTkTextbox(editor, height=160, width=260)
        kw_entry.pack(fill="x", pady=(4, 10))

        ctk.CTkLabel(editor, text="Primary category", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        ctk.CTkEntry(editor, textvariable=cat_var, width=260).pack(fill="x", pady=(4, 10))

        ctk.CTkLabel(editor, text="Notes", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        ctk.CTkEntry(editor, textvariable=notes_var, width=260).pack(fill="x", pady=(4, 10))

        def load_selection() -> None:
            sel = tree.selection()
            if not sel:
                return
            item_id = sel[0]
            values = tree.item(item_id, "values")
            if not values or len(values) < 2:
                return
            op_key = normalize_original_path_for_sidecar(values[1])
            idx = next(
                (
                    j
                    for j, r in enumerate(rows)
                    if normalize_original_path_for_sidecar(r.get("original_path", "")) == op_key
                ),
                None,
            )
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

            xmp_updated = 0
            skipped_no_path = 0
            skipped_no_xmp = 0
            skipped_write_error = 0
            no_xmp_sample_names: list[str] = []

            for r in rows:
                op = normalize_original_path_for_sidecar(r.get("original_path", ""))
                kw = r.get("suggested_keywords", "")
                cat = r.get("primary_category", "")
                if not op:
                    skipped_no_path += 1
                    continue
                xmp_path = xmp_sidecar_path_for_image(op)
                if not os.path.isfile(xmp_path):
                    skipped_no_xmp += 1
                    if len(no_xmp_sample_names) < 12:
                        no_xmp_sample_names.append(os.path.basename(op) or op)
                    continue
                try:
                    if rewrite_xmp_sidecar_if_exists(op, kw, cat):
                        xmp_updated += 1
                except Exception as exc:
                    skipped_write_error += 1
                    self._append_status(f"Could not write XMP for {os.path.basename(op)}: {exc}")

            xmp_skipped_total = skipped_no_path + skipped_no_xmp + skipped_write_error
            csv_name = os.path.basename(csv_path)
            self._append_status(f"CSV updated: {csv_path}")
            self._append_status(
                f"XMP sync: {xmp_updated} sidecar(s) rewritten next to originals; "
                f"{xmp_skipped_total} row(s) skipped (Lightroom-safe — image files unchanged)."
            )
            if skipped_no_path:
                self._append_status(
                    f"Skipped {skipped_no_path} row(s) with empty original_path (cannot locate sidecar)."
                )
            if skipped_no_xmp:
                sample = ", ".join(no_xmp_sample_names[:8])
                more = (
                    f" (+{skipped_no_xmp - len(no_xmp_sample_names)} more)"
                    if skipped_no_xmp > len(no_xmp_sample_names)
                    else ""
                )
                self._append_status(
                    f"No XMP sidecar beside file (skipped {skipped_no_xmp}): {sample}{more}"
                )

            messagebox.showinfo(
                win.title(),
                branding.REVIEW_SAVE_SUCCESS.format(
                    csv_basename=csv_name,
                    xmp_updated=xmp_updated,
                    xmp_skipped=xmp_skipped_total,
                ),
            )

        tree.bind("<<TreeviewSelect>>", lambda _e: load_selection())

        ctk.CTkButton(editor, text="Apply to selected row", command=apply_edits_to_selected).pack(fill="x", pady=(6, 6))
        ctk.CTkButton(
            editor,
            text=branding.BTN_REVIEW_SAVE,
            fg_color="#059669",
            hover_color="#047857",
            command=save_csv,
        ).pack(fill="x")


def main() -> None:
    app = PhotoMetadataApp()
    app.mainloop()


if __name__ == "__main__":
    main()

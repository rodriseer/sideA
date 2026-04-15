"""
Desktop GUI for Photo Metadata Assistant — Lightroom-safe metadata workflow.

Visual identity lives in theme.py; user-facing copy lives in branding.py.
This module is presentation-only: all processing is delegated to app.py,
classifier.py, organizer.py, etc.
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
from tkinter import Label as TkLabel, messagebox, ttk

from bundle_paths import get_resource_search_dirs, get_runtime_base_dir

# Add project root to path for PyInstaller / direct run
_base = get_runtime_base_dir() if getattr(sys, "frozen", False) else Path(__file__).parent
sys.path.insert(0, str(_base))

import branding
import theme as T
from app import format_summary, run_processing
from organizer import (
    normalize_original_path_for_sidecar,
    rewrite_xmp_sidecar_if_exists,
    xmp_sidecar_path_for_image,
)
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


# -----------------------------------------------------------------------------
# Global setup
# -----------------------------------------------------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")  # overridden by theme.py tokens below

_status_queue: queue.Queue = queue.Queue()

THUMB_SIZE = (180, 135)


# -----------------------------------------------------------------------------
# Resources
# -----------------------------------------------------------------------------

def _find_resource(names: tuple[str, ...]) -> Optional[Path]:
    """Look for a bundled resource under each search dir from bundle_paths."""
    for search_dir in get_resource_search_dirs():
        for name in names:
            p = search_dir / name
            if p.is_file():
                return p
    return None


def _load_logo_image(size_px: int = 56) -> Optional[ctk.CTkImage]:
    """Load the amber aperture logo as a CTkImage for crisp HiDPI rendering."""
    path = _find_resource((T.LOGO_FILENAME, "logo_128.png"))
    if not path:
        return None
    try:
        pil = Image.open(str(path)).convert("RGBA")
        return ctk.CTkImage(light_image=pil, dark_image=pil, size=(size_px, size_px))
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Status queue helpers
# -----------------------------------------------------------------------------

def _queue_status(msg: str) -> None:
    _status_queue.put(msg)


def _queue_progress(current: int, total: int, image_path: Optional[str] = None,
                    category: Optional[str] = None) -> None:
    _status_queue.put(("PROGRESS", current, total, image_path, category))


def _queue_result(success: bool, message: str, summary: Optional[Dict] = None) -> None:
    _status_queue.put(("RESULT", success, message, summary))


# -----------------------------------------------------------------------------
# Reusable UI building blocks
# -----------------------------------------------------------------------------

def _card(parent: Any, **kwargs: Any) -> ctk.CTkFrame:
    """A raised surface with consistent radius, background, and border."""
    return ctk.CTkFrame(
        parent,
        fg_color=T.BG_SURFACE,
        corner_radius=T.RADIUS_LG,
        border_width=1,
        border_color=T.BORDER_SUBTLE,
        **kwargs,
    )


def _primary_button(parent: Any, text: str, command: Any, *, large: bool = False,
                    icon: str = "") -> ctk.CTkButton:
    label = f"{icon}  {text}" if icon else text
    return ctk.CTkButton(
        parent,
        text=label,
        command=command,
        font=T.font(T.FONT_BUTTON),
        height=T.BUTTON_HEIGHT_LG if large else T.BUTTON_HEIGHT,
        corner_radius=T.RADIUS_MD,
        fg_color=T.ACCENT,
        hover_color=T.ACCENT_HOVER,
        text_color=T.ACCENT_FG,
    )


def _secondary_button(parent: Any, text: str, command: Any) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        font=T.font(T.FONT_BUTTON_SM),
        height=T.BUTTON_HEIGHT,
        corner_radius=T.RADIUS_MD,
        fg_color=T.NEUTRAL,
        hover_color=T.NEUTRAL_HOVER,
        text_color=T.TEXT_PRIMARY,
    )


def _success_button(parent: Any, text: str, command: Any) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        font=T.font(T.FONT_BUTTON_SM),
        height=T.BUTTON_HEIGHT,
        corner_radius=T.RADIUS_MD,
        fg_color=T.SUCCESS,
        hover_color=T.SUCCESS_HOVER,
        text_color=("#FFFFFF", "#0B1220"),
    )


def _step_number(parent: Any, n: int) -> ctk.CTkLabel:
    """Numbered circular badge used in the Setup Guide."""
    lbl = ctk.CTkLabel(
        parent,
        text=str(n),
        width=30,
        height=30,
        corner_radius=15,
        fg_color=T.ACCENT_SUBTLE,
        text_color=T.ACCENT,
        font=T.font(T.FONT_BODY_BOLD),
    )
    return lbl


def _pill(parent: Any, text: str, *, variant: str = "neutral") -> ctk.CTkLabel:
    """Small rounded status pill (Connected / Not connected / Working…)."""
    fg, txt = {
        "success": (T.SUCCESS_SUBTLE, T.SUCCESS),
        "danger":  (T.DANGER_SUBTLE,  T.DANGER),
        "warning": (T.WARNING_SUBTLE, T.WARNING),
        "info":    (T.INFO_SUBTLE,    T.INFO),
        "neutral": (T.BG_SURFACE_2,   T.TEXT_MUTED),
    }.get(variant, (T.BG_SURFACE_2, T.TEXT_MUTED))
    return ctk.CTkLabel(
        parent,
        text=text,
        fg_color=fg,
        text_color=txt,
        corner_radius=12,
        font=T.font(T.FONT_SMALL),
        padx=12, pady=4,
    )


# -----------------------------------------------------------------------------
# Setup Guide (credentials onboarding)
# -----------------------------------------------------------------------------

def open_setup_guide_window(parent: ctk.CTk, on_saved: Optional[Any] = None) -> None:
    """Modal onboarding window that walks through Google Vision setup."""
    win = ctk.CTkToplevel(parent)
    win.title(branding.SETUP_GUIDE_TITLE)
    win.geometry("640x820")
    win.minsize(560, 700)
    win.transient(parent)
    win.grab_set()
    win.configure(fg_color=T.BG_CANVAS)

    root = ctk.CTkFrame(win, fg_color=T.BG_CANVAS, corner_radius=0)
    root.pack(fill="both", expand=True)

    raw_saved = get_configured_credentials_path_raw()
    selected_path = ctk.StringVar(value=get_saved_credentials_path() or raw_saved)
    test_detail_var = ctk.StringVar(value="")
    status_var = ctk.StringVar(value=branding.CREDENTIALS_STATUS_NOT_CONFIGURED)

    # --- Header ------------------------------------------------------------
    header = ctk.CTkFrame(root, fg_color="transparent")
    header.pack(fill="x", padx=T.SPACE_XL, pady=(T.SPACE_XL, T.SPACE_MD))

    ctk.CTkLabel(
        header,
        text=branding.SETUP_GUIDE_TITLE,
        font=T.font(T.FONT_HEADING),
        text_color=T.TEXT_PRIMARY,
    ).pack(anchor="w")
    ctk.CTkLabel(
        header,
        text=branding.SETUP_GUIDE_SUBTITLE,
        font=T.font(T.FONT_BODY),
        text_color=T.TEXT_MUTED,
    ).pack(anchor="w", pady=(4, T.SPACE_MD))

    status_pill_wrap = ctk.CTkFrame(header, fg_color="transparent")
    status_pill_wrap.pack(anchor="w")
    status_pill = _pill(status_pill_wrap, status_var.get(), variant="danger")
    status_pill.pack(anchor="w")

    def refresh_status_pill() -> None:
        apply_saved_credentials_to_environment()
        ok, _, _ = check_vision_credentials()
        if ok:
            status_var.set(branding.CREDENTIALS_STATUS_CONFIGURED)
            status_pill.configure(
                text=status_var.get(),
                fg_color=T.SUCCESS_SUBTLE, text_color=T.SUCCESS,
            )
        else:
            status_var.set(branding.CREDENTIALS_STATUS_NOT_CONFIGURED)
            status_pill.configure(
                text=status_var.get(),
                fg_color=T.DANGER_SUBTLE, text_color=T.DANGER,
            )

    # --- Scrollable steps --------------------------------------------------
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
        row.pack(fill="x", pady=(0, T.SPACE_MD))
        _step_number(row, i).pack(side="left", anchor="nw", padx=(0, T.SPACE_MD))
        ctk.CTkLabel(
            row,
            text=body,
            font=T.font(T.FONT_BODY),
            text_color=T.TEXT_SECONDARY,
            wraplength=500,
            justify="left",
            anchor="w",
        ).pack(side="left", fill="x", expand=True, pady=(4, 0))

        if i == 1:
            link = ctk.CTkLabel(
                scroll,
                text=branding.SETUP_GUIDE_LINK_TEXT + "  →",
                font=T.font(T.FONT_BODY_BOLD),
                text_color=T.ACCENT,
                cursor="hand2",
            )
            link.pack(anchor="w", padx=(46, 0), pady=(0, T.SPACE_MD))
            link.bind("<Button-1>", lambda _e: webbrowser.open(branding.SETUP_GUIDE_CLOUD_URL))

    ctk.CTkLabel(
        scroll,
        text=branding.SETUP_GUIDE_PRIVACY_WARNING,
        font=T.font(T.FONT_SMALL),
        text_color=T.WARNING,
        wraplength=520,
        justify="left",
    ).pack(anchor="w", pady=(T.SPACE_SM, T.SPACE_XS))

    ctk.CTkLabel(
        scroll,
        text=f"{branding.CREDENTIALS_CONFIG_HINT}\n{get_config_path()}",
        font=T.font(T.FONT_TINY),
        text_color=T.TEXT_SUBTLE,
        wraplength=520,
        justify="left",
    ).pack(anchor="w", pady=(T.SPACE_MD, T.SPACE_SM))

    # --- Footer actions ----------------------------------------------------
    footer = ctk.CTkFrame(root, fg_color=T.BG_SURFACE, corner_radius=0)
    foot_inner = ctk.CTkFrame(footer, fg_color="transparent")
    foot_inner.pack(fill="x", padx=T.SPACE_XL, pady=(T.SPACE_LG, T.SPACE_XL))

    path_display = ctk.CTkLabel(
        foot_inner,
        text="",
        font=T.font(T.FONT_SMALL),
        text_color=T.TEXT_MUTED,
    )
    path_display.pack(anchor="w", pady=(0, T.SPACE_SM))

    def update_path_display() -> None:
        p = selected_path.get().strip()
        if p and os.path.isfile(p):
            path_display.configure(text=os.path.basename(p))
        else:
            path_display.configure(text=branding.SETUP_GUIDE_PATH_HINT)
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

    _primary_button(foot_inner, branding.BTN_SELECT_CREDENTIALS_JSON, browse,
                    large=True).pack(fill="x", pady=(0, T.SPACE_SM))

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
                    refresh_status_pill()
                    if on_saved:
                        on_saved()
                else:
                    apply_saved_credentials_to_environment()
                    test_detail_var.set((str(payload) or branding.CREDENTIALS_FAILURE)[:400])
                    refresh_status_pill()
            except queue.Empty:
                win.after(150, poll)

        test_detail_var.set(branding.CREDENTIALS_TESTING)
        poll()

    _secondary_button(foot_inner, branding.BTN_TEST_CONNECTION,
                      do_test_connection).pack(fill="x", pady=(0, T.SPACE_SM))

    ctk.CTkLabel(
        foot_inner,
        textvariable=test_detail_var,
        font=T.font(T.FONT_SMALL),
        text_color=T.TEXT_SECONDARY,
        wraplength=540,
        justify="left",
    ).pack(anchor="w", pady=(T.SPACE_XS, 0))

    footer.pack(fill="x", side="bottom")
    scroll.pack(fill="both", expand=True, padx=T.SPACE_XL, pady=(0, T.SPACE_SM))

    refresh_status_pill()
    if not get_saved_credentials_path() and selected_path.get().strip():
        test_detail_var.set(branding.SETUP_GUIDE_TEST_TO_FINISH)


# -----------------------------------------------------------------------------
# Main window
# -----------------------------------------------------------------------------

class PhotoMetadataApp(ctk.CTk):
    """Main window — header with logo, three step cards, activity panel."""

    def __init__(self) -> None:
        super().__init__()

        self.title(branding.WINDOW_TITLE)
        self.geometry(f"{T.WINDOW_DEFAULT_W}x{T.WINDOW_DEFAULT_H}")
        self.minsize(T.WINDOW_MIN_W, T.WINDOW_MIN_H)
        self.configure(fg_color=T.BG_CANVAS)

        self.photos_folder = ctk.StringVar(value="")
        self._output_folder_after_done: Optional[str] = None
        self._suggested_keywords_csv_after_done: Optional[str] = None
        self._thumb_photo: Any = None
        self._logo_image = _load_logo_image(48)
        self._is_processing = False
        self._first_run_credentials_prompt_shown = False

        apply_saved_credentials_to_environment()

        self._build_menubar()
        self._build_ui()
        self._refresh_credentials_status()
        self._start_queue_poll()
        self.after(450, self._maybe_show_first_run_credentials_prompt)

    # --- Menubar -----------------------------------------------------------

    def _build_menubar(self) -> None:
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

    def _show_about(self) -> None:
        messagebox.showinfo(f"About {branding.APP_NAME}", branding.ABOUT_BLURB)

    # --- Layout ------------------------------------------------------------

    def _build_ui(self) -> None:
        # Outer scroll so small screens still reach the bottom
        outer = ctk.CTkScrollableFrame(self, fg_color=T.BG_CANVAS)
        outer.pack(fill="both", expand=True, padx=0, pady=0)

        container = ctk.CTkFrame(outer, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=T.SPACE_XL, pady=T.SPACE_XL)

        self._build_header(container)
        self._build_credentials_card(container)
        self._build_folder_card(container)
        self._build_run_card(container)
        self._build_results_bar(container)
        self._build_activity_card(container)
        self._build_footer(container)

    def _build_header(self, parent: Any) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(0, T.SPACE_LG))

        # Logo + wordmark (left)
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left")
        if self._logo_image is not None:
            ctk.CTkLabel(left, text="", image=self._logo_image).pack(side="left", padx=(0, T.SPACE_MD))
        text_col = ctk.CTkFrame(left, fg_color="transparent")
        text_col.pack(side="left")
        ctk.CTkLabel(
            text_col,
            text=branding.APP_NAME,
            font=T.font(T.FONT_HEADING),
            text_color=T.TEXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            text_col,
            text=T.BRAND_TAGLINE,
            font=T.font(T.FONT_SMALL),
            text_color=T.TEXT_MUTED,
        ).pack(anchor="w")

        # Safety note on the right
        safety = ctk.CTkLabel(
            header,
            text=branding.APP_SAFETY_BADGE,
            font=T.font(T.FONT_SMALL),
            text_color=T.INFO,
            fg_color=T.INFO_SUBTLE,
            corner_radius=12,
            padx=14, pady=6,
        )
        safety.pack(side="right")

    # --- Card 1: credentials ----------------------------------------------

    def _build_credentials_card(self, parent: Any) -> None:
        card = _card(parent)
        card.pack(fill="x", pady=(0, T.SPACE_MD))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=T.SPACE_LG, pady=T.SPACE_LG)

        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")

        ctk.CTkLabel(
            top,
            text=branding.CARD_CREDENTIALS_TITLE,
            font=T.font(T.FONT_SUBHEAD),
            text_color=T.TEXT_PRIMARY,
        ).pack(side="left")

        self._cred_pill = _pill(top, branding.CREDENTIALS_STATUS_NOT_CONFIGURED, variant="danger")
        self._cred_pill.pack(side="right")

        self._cred_hint = ctk.CTkLabel(
            inner,
            text=branding.CARD_CREDENTIALS_BODY,
            font=T.font(T.FONT_BODY),
            text_color=T.TEXT_SECONDARY,
            wraplength=640,
            justify="left",
            anchor="w",
        )
        self._cred_hint.pack(fill="x", pady=(T.SPACE_SM, T.SPACE_MD))

        _primary_button(
            inner,
            branding.BTN_SETUP_GUIDE,
            command=lambda: open_setup_guide_window(self, self._refresh_credentials_status),
        ).pack(fill="x")

    # --- Card 2: folder picker --------------------------------------------

    def _build_folder_card(self, parent: Any) -> None:
        card = _card(parent)
        card.pack(fill="x", pady=(0, T.SPACE_MD))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=T.SPACE_LG, pady=T.SPACE_LG)

        ctk.CTkLabel(
            inner,
            text=branding.CARD_FOLDER_TITLE,
            font=T.font(T.FONT_SUBHEAD),
            text_color=T.TEXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            inner,
            text=branding.CARD_FOLDER_BODY,
            font=T.font(T.FONT_SMALL),
            text_color=T.TEXT_MUTED,
            wraplength=640,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(T.SPACE_XS, T.SPACE_MD))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        self._folder_entry = ctk.CTkEntry(
            row,
            textvariable=self.photos_folder,
            placeholder_text=branding.PLACEHOLDER_PHOTOS_FOLDER,
            height=T.INPUT_HEIGHT,
            font=T.font(T.FONT_BODY),
            corner_radius=T.RADIUS_MD,
            border_color=T.BORDER_STRONG,
        )
        self._folder_entry.pack(side="left", fill="x", expand=True, padx=(0, T.SPACE_SM))
        self._browse_btn = _secondary_button(row, branding.BTN_BROWSE_FOLDER, self._select_folder)
        self._browse_btn.configure(width=130)
        self._browse_btn.pack(side="left")

    # --- Card 3: run -------------------------------------------------------

    def _build_run_card(self, parent: Any) -> None:
        card = _card(parent)
        card.pack(fill="x", pady=(0, T.SPACE_MD))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=T.SPACE_LG, pady=T.SPACE_LG)

        ctk.CTkLabel(
            inner,
            text=branding.CARD_RUN_TITLE,
            font=T.font(T.FONT_SUBHEAD),
            text_color=T.TEXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            inner,
            text=branding.CARD_RUN_BODY,
            font=T.font(T.FONT_SMALL),
            text_color=T.TEXT_MUTED,
            wraplength=640,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(T.SPACE_XS, T.SPACE_MD))

        self._start_btn = _primary_button(
            inner, branding.BTN_START_ANALYSIS, self._on_start, large=True,
        )
        self._start_btn.pack(fill="x")

        # Progress block — hidden until a run starts
        self._progress_block = ctk.CTkFrame(inner, fg_color="transparent")
        self._progress_block.pack(fill="x", pady=(T.SPACE_MD, 0))

        progress_row = ctk.CTkFrame(self._progress_block, fg_color="transparent")
        progress_row.pack(fill="x")

        self._thumb_frame = ctk.CTkFrame(
            progress_row,
            fg_color=T.BG_SURFACE_2,
            corner_radius=T.RADIUS_MD,
            width=THUMB_SIZE[0] + 12,
            height=THUMB_SIZE[1] + 12,
        )
        self._thumb_frame.pack(side="left", padx=(0, T.SPACE_MD))
        self._thumb_frame.pack_propagate(False)
        self._thumb_label = TkLabel(
            self._thumb_frame,
            text="",
            bg="#1F2937",
            fg="#94A3B8",
            font=(T.FONT_FAMILY, 10),
        )
        self._thumb_label.place(relx=0.5, rely=0.5, anchor="center")

        right_col = ctk.CTkFrame(progress_row, fg_color="transparent")
        right_col.pack(side="left", fill="both", expand=True)

        self._counter_label = ctk.CTkLabel(
            right_col, text="",
            font=T.font(T.FONT_BODY_BOLD),
            text_color=T.TEXT_PRIMARY,
            anchor="w",
        )
        self._counter_label.pack(fill="x")

        self._detected_label = ctk.CTkLabel(
            right_col, text="",
            font=T.font(T.FONT_SMALL),
            text_color=T.ACCENT,
            anchor="w",
        )
        self._detected_label.pack(fill="x", pady=(2, T.SPACE_SM))

        self._progress = ctk.CTkProgressBar(
            right_col, height=10, corner_radius=5,
            progress_color=T.ACCENT,
            fg_color=T.BG_SURFACE_2,
        )
        self._progress.pack(fill="x")
        self._progress.set(0)

        # Hide until needed
        self._progress_block.pack_forget()

    # --- Results bar -------------------------------------------------------

    def _build_results_bar(self, parent: Any) -> None:
        self._results_bar = ctk.CTkFrame(parent, fg_color="transparent")
        # packed on completion

        row = ctk.CTkFrame(self._results_bar, fg_color="transparent")
        row.pack(fill="x")

        self._open_btn = _success_button(row, branding.BTN_OPEN_RESULTS, self._open_output_folder)
        self._open_btn.pack(side="left", fill="x", expand=True, padx=(0, T.SPACE_SM))

        self._review_btn = ctk.CTkButton(
            row,
            text=branding.BTN_REVIEW_KEYWORDS,
            command=self._open_review_window,
            font=T.font(T.FONT_BUTTON_SM),
            height=T.BUTTON_HEIGHT,
            corner_radius=T.RADIUS_MD,
            fg_color=T.NEUTRAL,
            hover_color=T.NEUTRAL_HOVER,
            text_color=T.TEXT_PRIMARY,
        )
        self._review_btn.pack(side="left", fill="x", expand=True)

    # --- Activity log ------------------------------------------------------

    def _build_activity_card(self, parent: Any) -> None:
        card = _card(parent)
        card.pack(fill="both", expand=True, pady=(T.SPACE_MD, 0))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=T.SPACE_LG, pady=T.SPACE_LG)

        ctk.CTkLabel(
            inner,
            text=branding.LABEL_STATUS,
            font=T.font(T.FONT_BODY_BOLD),
            text_color=T.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, T.SPACE_SM))

        self._status_text = ctk.CTkTextbox(
            inner,
            height=140,
            font=ctk.CTkFont(family=T.FONT_FAMILY_MONO, size=12),
            state="disabled",
            fg_color=T.BG_SURFACE_2,
            text_color=T.TEXT_SECONDARY,
            corner_radius=T.RADIUS_SM,
            border_width=1,
            border_color=T.BORDER_SUBTLE,
        )
        self._status_text.pack(fill="both", expand=True)

    def _build_footer(self, parent: Any) -> None:
        ctk.CTkLabel(
            parent,
            text=branding.APP_TRUST_NOTE,
            font=T.font(T.FONT_TINY),
            text_color=T.TEXT_SUBTLE,
            wraplength=640,
            justify="center",
        ).pack(fill="x", pady=(T.SPACE_LG, 0))

    # --- Credentials state -------------------------------------------------

    def _sync_start_button_for_credentials(self) -> None:
        if self._is_processing:
            return
        ok, _, _ = check_vision_credentials()
        self._start_btn.configure(state="normal" if ok else "disabled")

    def _refresh_credentials_status(self) -> None:
        apply_saved_credentials_to_environment()
        ok, _, _ = check_vision_credentials()
        if ok:
            self._cred_pill.configure(
                text=branding.CREDENTIALS_STATUS_CONFIGURED,
                fg_color=T.SUCCESS_SUBTLE,
                text_color=T.SUCCESS,
            )
            self._cred_hint.configure(
                text=branding.CARD_CREDENTIALS_BODY_CONNECTED,
                text_color=T.TEXT_SECONDARY,
            )
        else:
            self._cred_pill.configure(
                text=branding.CREDENTIALS_STATUS_NOT_CONFIGURED,
                fg_color=T.DANGER_SUBTLE,
                text_color=T.DANGER,
            )
            self._cred_hint.configure(
                text=branding.CARD_CREDENTIALS_BODY,
                text_color=T.TEXT_SECONDARY,
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
        win.geometry("480x320")
        win.minsize(440, 280)
        win.transient(self)
        win.grab_set()
        win.focus_force()
        win.configure(fg_color=T.BG_CANVAS)

        frame = ctk.CTkFrame(win, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=T.SPACE_LG, pady=T.SPACE_LG)

        ctk.CTkLabel(
            frame, text=branding.FIRST_RUN_TITLE,
            font=T.font(T.FONT_HEADING),
            text_color=T.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, T.SPACE_SM))
        ctk.CTkLabel(
            frame, text=branding.FIRST_RUN_BODY,
            font=T.font(T.FONT_BODY),
            text_color=T.TEXT_SECONDARY,
            wraplength=420, justify="left",
        ).pack(anchor="w", pady=(0, T.SPACE_LG))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x")

        def open_setup() -> None:
            win.destroy()
            open_setup_guide_window(self, self._refresh_credentials_status)

        _primary_button(row, branding.FIRST_RUN_BTN_SETUP, open_setup).pack(
            side="left", padx=(0, T.SPACE_SM))
        _secondary_button(row, branding.FIRST_RUN_BTN_LATER, win.destroy).pack(side="left")

    # --- Folder / processing ----------------------------------------------

    def _select_folder(self) -> None:
        path = ctk.filedialog.askdirectory(title="Select folder with photos or RAW files")
        if path:
            self.photos_folder.set(path)

    def _set_processing_state(self, processing: bool) -> None:
        self._is_processing = processing
        state = "disabled" if processing else "normal"
        self._browse_btn.configure(state=state)
        self._folder_entry.configure(state=state)
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
            self._detected_label.configure(text=f"Detected category: {category}")
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
                        self._counter_label.configure(
                            text=f"Analyzing image {current} of {total}")
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
            messagebox.showwarning(
                branding.CARD_CREDENTIALS_TITLE, branding.CREDENTIALS_MISSING_GUI,
            )
            self._refresh_credentials_status()
            return

        output_dir = os.path.join(folder, branding.OUTPUTS_SUBFOLDER)

        self._set_processing_state(True)
        self._start_btn.configure(text=branding.BTN_WORKING)
        self._progress.set(0)
        self._progress_block.pack(fill="x", pady=(T.SPACE_MD, 0))
        self._counter_label.configure(text=branding.MSG_STARTING)
        self._detected_label.configure(text="")
        self._show_thumbnail(None, None)
        self._status_text.configure(state="normal")
        self._status_text.delete("1.0", "end")
        self._status_text.configure(state="disabled")
        self._results_bar.pack_forget()

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
                        "credentials", "default credentials", "authentication",
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
        self._start_btn.configure(text=branding.BTN_START_ANALYSIS)
        self._progress.set(1.0)
        self._refresh_credentials_status()

        if success and summary:
            self._counter_label.configure(text=branding.MSG_COMPLETE)
            self._detected_label.configure(text="")
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
                self._results_bar.pack(fill="x", pady=(T.SPACE_MD, 0))
        elif success:
            self._counter_label.configure(text=branding.MSG_COMPLETE)
            folder = self.photos_folder.get().strip()
            self._output_folder_after_done = os.path.join(folder, branding.OUTPUTS_SUBFOLDER)
            if os.path.isdir(self._output_folder_after_done):
                self._results_bar.pack(fill="x", pady=(T.SPACE_MD, 0))
        else:
            self._counter_label.configure(text=branding.MSG_ERROR)
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

    # --- Review window -----------------------------------------------------

    def _open_review_window(self) -> None:
        csv_path = self._suggested_keywords_csv_after_done or ""
        if not csv_path or not os.path.isfile(csv_path):
            self._append_status("Could not find suggested_keywords.csv to review.")
            return

        win = ctk.CTkToplevel(self)
        win.title(f"{branding.APP_NAME} — {branding.BTN_REVIEW_KEYWORDS}")
        win.geometry("980x580")
        win.configure(fg_color=T.BG_CANVAS)

        container = ctk.CTkFrame(win, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=T.SPACE_LG, pady=T.SPACE_LG)

        ctk.CTkLabel(
            container,
            text=branding.REVIEW_INTRO_XMP,
            font=T.font(T.FONT_SMALL),
            text_color=T.TEXT_SECONDARY,
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(0, T.SPACE_MD))

        body = ctk.CTkFrame(container, fg_color="transparent")
        body.pack(fill="both", expand=True)

        columns = ("filename", "original_path", "suggested_keywords",
                   "primary_category", "notes")
        tree = ttk.Treeview(body, columns=columns, show="headings", height=15)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=160 if col != "original_path" else 280, stretch=True)

        yscroll = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
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

        editor = ctk.CTkFrame(body, fg_color=T.BG_SURFACE, corner_radius=T.RADIUS_LG,
                              border_width=1, border_color=T.BORDER_SUBTLE)
        editor.pack(side="left", fill="y", padx=(T.SPACE_MD, 0))
        ed_inner = ctk.CTkFrame(editor, fg_color="transparent")
        ed_inner.pack(fill="both", expand=True, padx=T.SPACE_MD, pady=T.SPACE_MD)

        selected_idx: dict[str, Optional[int]] = {"i": None}
        cat_var = ctk.StringVar(value="")
        notes_var = ctk.StringVar(value="")

        ctk.CTkLabel(ed_inner, text="Suggested keywords",
                     font=T.font(T.FONT_BODY_BOLD),
                     text_color=T.TEXT_PRIMARY).pack(anchor="w")
        kw_entry = ctk.CTkTextbox(ed_inner, height=160, width=280,
                                  fg_color=T.BG_SURFACE_2,
                                  text_color=T.TEXT_PRIMARY)
        kw_entry.pack(fill="x", pady=(4, T.SPACE_SM))

        ctk.CTkLabel(ed_inner, text="Primary category",
                     font=T.font(T.FONT_BODY_BOLD),
                     text_color=T.TEXT_PRIMARY).pack(anchor="w")
        ctk.CTkEntry(ed_inner, textvariable=cat_var, width=280,
                     height=T.INPUT_HEIGHT).pack(fill="x", pady=(4, T.SPACE_SM))

        ctk.CTkLabel(ed_inner, text="Notes",
                     font=T.font(T.FONT_BODY_BOLD),
                     text_color=T.TEXT_PRIMARY).pack(anchor="w")
        ctk.CTkEntry(ed_inner, textvariable=notes_var, width=280,
                     height=T.INPUT_HEIGHT).pack(fill="x", pady=(4, T.SPACE_MD))

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
                (j for j, r in enumerate(rows)
                 if normalize_original_path_for_sidecar(r.get("original_path", "")) == op_key),
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
            tree.item(item_id, values=(
                rows[idx]["filename"], rows[idx]["original_path"],
                rows[idx]["suggested_keywords"], rows[idx]["primary_category"],
                rows[idx]["notes"],
            ))

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
                    self._append_status(
                        f"Could not write XMP for {os.path.basename(op)}: {exc}")

            xmp_skipped_total = skipped_no_path + skipped_no_xmp + skipped_write_error
            csv_name = os.path.basename(csv_path)
            self._append_status(f"CSV updated: {csv_path}")
            self._append_status(
                f"XMP sync: {xmp_updated} sidecar(s) rewritten next to originals; "
                f"{xmp_skipped_total} row(s) skipped (Lightroom-safe — image files unchanged)."
            )
            if skipped_no_path:
                self._append_status(
                    f"Skipped {skipped_no_path} row(s) with empty original_path (cannot locate sidecar).")
            if skipped_no_xmp:
                sample = ", ".join(no_xmp_sample_names[:8])
                more = (f" (+{skipped_no_xmp - len(no_xmp_sample_names)} more)"
                        if skipped_no_xmp > len(no_xmp_sample_names) else "")
                self._append_status(
                    f"No XMP sidecar beside file (skipped {skipped_no_xmp}): {sample}{more}")

            messagebox.showinfo(
                win.title(),
                branding.REVIEW_SAVE_SUCCESS.format(
                    csv_basename=csv_name,
                    xmp_updated=xmp_updated,
                    xmp_skipped=xmp_skipped_total,
                ),
            )

        tree.bind("<<TreeviewSelect>>", lambda _e: load_selection())

        _secondary_button(ed_inner, "Apply to selected row",
                          apply_edits_to_selected).pack(fill="x", pady=(T.SPACE_XS, T.SPACE_SM))
        _success_button(ed_inner, branding.BTN_REVIEW_SAVE, save_csv).pack(fill="x")


def main() -> None:
    app = PhotoMetadataApp()
    app.mainloop()


if __name__ == "__main__":
    main()

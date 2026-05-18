import contextlib
import csv
import io
import os
import queue
import subprocess
import sys
import threading
import time
from tkinter import messagebox, ttk
from typing import Callable, List, Tuple

import customtkinter as ctk

import main as backend


class QueueWriter(io.TextIOBase):
    def __init__(self, log_queue: "queue.Queue[str]") -> None:
        self.log_queue = log_queue

    def write(self, text: str) -> int:
        if text and not text.isspace():
            self.log_queue.put(text)
        return len(text)

    def flush(self) -> None:
        pass


class ExternalMergeSortGUI(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("External Merge Sort - Employee Records")
        self.geometry("1200x760")
        self.minsize(1000, 680)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.worker_running = False

        self.status_value = ctk.StringVar(value="Idle")
        self.files_value = ctk.StringVar(value="0")
        self.records_value = ctk.StringVar(value="0")
        self.time_value = ctk.StringVar(value="0.0000 s")

        self._build_ui()
        self._setup_treeview_style()
        self._refresh_stats()
        self._load_final_preview()
        self.after(120, self._drain_log_queue)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        self.grid_rowconfigure(5, weight=2)

        title = ctk.CTkLabel(
            self,
            text="External Merge Sort for Large Employee Records",
            font=ctk.CTkFont(size=28, weight="bold"),
        )
        title.grid(row=0, column=0, padx=20, pady=(16, 12), sticky="w")

        button_frame = ctk.CTkFrame(self, corner_radius=16)
        button_frame.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="ew")
        for col in range(5):
            button_frame.grid_columnconfigure(col, weight=1)

        self.generate_btn = ctk.CTkButton(
            button_frame,
            text="Generate Data",
            corner_radius=12,
            command=self._on_generate,
        )
        self.generate_btn.grid(row=0, column=0, padx=8, pady=12, sticky="ew")

        self.phase1_btn = ctk.CTkButton(
            button_frame,
            text="Run Phase 1 Sorting",
            corner_radius=12,
            command=self._on_phase_1,
        )
        self.phase1_btn.grid(row=0, column=1, padx=8, pady=12, sticky="ew")

        self.phase2_btn = ctk.CTkButton(
            button_frame,
            text="Run Phase 2 Merge",
            corner_radius=12,
            command=self._on_phase_2,
        )
        self.phase2_btn.grid(row=0, column=2, padx=8, pady=12, sticky="ew")

        self.full_btn = ctk.CTkButton(
            button_frame,
            text="Run Full Pipeline",
            corner_radius=12,
            command=self._on_full_pipeline,
        )
        self.full_btn.grid(row=0, column=3, padx=8, pady=12, sticky="ew")

        self.open_btn = ctk.CTkButton(
            button_frame,
            text="Open Final Output File",
            corner_radius=12,
            command=self._open_final_output_file,
        )
        self.open_btn.grid(row=0, column=4, padx=8, pady=12, sticky="ew")

        self.progress = ctk.CTkProgressBar(self)
        self.progress.grid(row=2, column=0, padx=20, pady=(0, 12), sticky="ew")
        self.progress.set(0)

        info_frame = ctk.CTkFrame(self, corner_radius=16)
        info_frame.grid(row=3, column=0, padx=20, pady=(0, 12), sticky="ew")
        for col in range(4):
            info_frame.grid_columnconfigure(col, weight=1)

        self._stat_cell(info_frame, "Total Files", self.files_value, 0)
        self._stat_cell(info_frame, "Total Records", self.records_value, 1)
        self._stat_cell(info_frame, "Execution Time", self.time_value, 2)
        self._stat_cell(info_frame, "Current Status", self.status_value, 3)

        logs_frame = ctk.CTkFrame(self, corner_radius=16)
        logs_frame.grid(row=4, column=0, padx=20, pady=(0, 12), sticky="nsew")
        logs_frame.grid_rowconfigure(1, weight=1)
        logs_frame.grid_columnconfigure(0, weight=1)

        logs_title = ctk.CTkLabel(
            logs_frame, text="Program Output / Execution Logs", font=ctk.CTkFont(size=16, weight="bold")
        )
        logs_title.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="w")

        self.log_box = ctk.CTkTextbox(logs_frame, corner_radius=12, wrap="word")
        self.log_box.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")

        preview_frame = ctk.CTkFrame(self, corner_radius=16)
        preview_frame.grid(row=5, column=0, padx=20, pady=(0, 16), sticky="nsew")
        preview_frame.grid_rowconfigure(1, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)

        preview_title = ctk.CTkLabel(
            preview_frame,
            text="Preview: output/final_sorted_employees.csv",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        preview_title.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="w")

        table_container = ctk.CTkFrame(preview_frame, fg_color="transparent")
        table_container.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        table_container.grid_rowconfigure(0, weight=1)
        table_container.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(table_container, show="headings")
        self.tree.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(table_container, orient="vertical", command=self.tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=y_scroll.set)

    def _stat_cell(self, parent: ctk.CTkFrame, label: str, var: ctk.StringVar, column: int) -> None:
        card = ctk.CTkFrame(parent, corner_radius=12)
        card.grid(row=0, column=column, padx=8, pady=10, sticky="ew")
        ctk.CTkLabel(card, text=label, text_color="#9ca3af").pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(card, textvariable=var, font=ctk.CTkFont(size=18, weight="bold")).pack(
            anchor="w", padx=10, pady=(0, 10)
        )

    def _setup_treeview_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#111827",
            fieldbackground="#111827",
            foreground="#f3f4f6",
            rowheight=24,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background="#1f2937",
            foreground="#f3f4f6",
            relief="flat",
        )
        style.map("Treeview", background=[("selected", "#2563eb")], foreground=[("selected", "#ffffff")])

    def _append_log(self, text: str) -> None:
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")

    def _drain_log_queue(self) -> None:
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(line.rstrip("\n"))
        self.after(120, self._drain_log_queue)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in [self.generate_btn, self.phase1_btn, self.phase2_btn, self.full_btn]:
            button.configure(state=state)

    def _set_status(self, text: str) -> None:
        self.status_value.set(text)

    def _run_async(self, title: str, tasks: List[Tuple[str, Callable[[], None]]]) -> None:
        if self.worker_running:
            messagebox.showinfo("Please Wait", "Another task is still running.")
            return

        self.worker_running = True
        self._set_buttons_enabled(False)
        self.progress.set(0)
        self.time_value.set("0.0000 s")
        self._set_status(f"{title} started...")
        self._append_log(f"[INFO] {title} started.")

        total_steps = max(1, len(tasks))

        def worker() -> None:
            start = time.time()
            ok = True
            writer = QueueWriter(self.log_queue)
            try:
                with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                    for idx, (label, fn) in enumerate(tasks, start=1):
                        self.log_queue.put(f"\n--- {label} ---")
                        fn()
                        self.after(0, self.progress.set, idx / total_steps)
            except (FileNotFoundError, PermissionError, ValueError, OSError) as exc:
                ok = False
                self.log_queue.put(f"[ERROR] {type(exc).__name__}: {exc}")
            except Exception as exc:  # noqa: BLE001
                ok = False
                self.log_queue.put(f"[ERROR] Unexpected {type(exc).__name__}: {exc}")

            elapsed = time.time() - start
            self.after(0, self._finish_run, title, ok, elapsed)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_run(self, title: str, ok: bool, elapsed: float) -> None:
        self.worker_running = False
        self._set_buttons_enabled(True)
        self.time_value.set(f"{elapsed:.4f} s")
        self._refresh_stats()
        self._load_final_preview()

        if ok:
            self._set_status(f"{title} completed")
            self._append_log(f"[DONE] {title} completed in {elapsed:.4f} seconds.")
        else:
            self._set_status(f"{title} failed")
            self._append_log(f"[FAILED] {title} failed after {elapsed:.4f} seconds.")

    def _count_csv_records(self, file_path: str) -> int:
        if not os.path.exists(file_path):
            return 0
        with open(file_path, mode="r", newline="", encoding="utf-8") as csv_file:
            reader = csv.reader(csv_file)
            next(reader, None)
            return sum(1 for _ in reader)

    def _refresh_stats(self) -> None:
        data_files = [
            file_name
            for file_name in os.listdir(backend.DATA_DIR)
            if file_name.startswith("data_") and file_name.endswith(".csv")
        ]
        self.files_value.set(str(len(data_files)))

        final_file = os.path.join(backend.FINAL_OUTPUT_DIR, "final_sorted_employees.csv")
        if os.path.exists(final_file):
            records = self._count_csv_records(final_file)
        else:
            records = sum(
                self._count_csv_records(os.path.join(backend.DATA_DIR, file_name))
                for file_name in data_files
            )
        self.records_value.set(str(records))

    def _load_final_preview(self, max_rows: int = 120) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        final_file = os.path.join(backend.FINAL_OUTPUT_DIR, "final_sorted_employees.csv")
        if not os.path.exists(final_file):
            self.tree.configure(columns=())
            return

        with open(final_file, mode="r", newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            columns = reader.fieldnames or []
            self.tree.configure(columns=columns)

            for column in columns:
                self.tree.heading(column, text=column)
                self.tree.column(column, anchor="center", width=170, stretch=True)

            for idx, row in enumerate(reader):
                if idx >= max_rows:
                    break
                self.tree.insert("", "end", values=[row.get(column, "") for column in columns])

    def _on_generate(self) -> None:
        self._run_async("Generate Data", [("Generating dummy data", backend.generate_dummy_data)])

    def _on_phase_1(self) -> None:
        self._run_async("Phase 1 Sorting", [("Sorting chunk files", backend.phase_1_sort_chunks)])

    def _on_phase_2(self) -> None:
        self._run_async("Phase 2 Merge", [("Merging sorted chunks", backend.phase_2_multi_way_merge)])

    def _on_full_pipeline(self) -> None:
        self._run_async(
            "Full Pipeline",
            [
                ("Generating dummy data", backend.generate_dummy_data),
                ("Phase 1 sorting", backend.phase_1_sort_chunks),
                ("Phase 2 merge", backend.phase_2_multi_way_merge),
            ],
        )

    def _open_final_output_file(self) -> None:
        final_file = os.path.join(backend.FINAL_OUTPUT_DIR, "final_sorted_employees.csv")
        safe_root = os.path.abspath(backend.FINAL_OUTPUT_DIR)
        safe_path = os.path.abspath(final_file)
        if not os.path.exists(final_file):
            messagebox.showwarning("File Not Found", "Run Phase 2 Merge first to create the final output file.")
            return
        try:
            is_outside = os.path.commonpath([safe_root, safe_path]) != safe_root
        except ValueError:
            is_outside = True
        if is_outside:
            messagebox.showerror("Invalid Path", "Resolved output path is outside the expected output directory.")
            return

        try:
            if sys.platform.startswith("win"):
                os.startfile(safe_path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", safe_path], check=False)
            else:
                subprocess.run(["xdg-open", safe_path], check=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Open File Error",
                f"Failed to open final_sorted_employees.csv:\n{type(exc).__name__}: {exc}",
            )


if __name__ == "__main__":
    app = ExternalMergeSortGUI()
    app.mainloop()

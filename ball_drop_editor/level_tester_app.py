from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from .level_tester_core import BallDropSimulator, DeepSearchSolver, SolveResult, iter_json_files

DEFAULT_TEST_FOLDER = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "30_Levels_1stRelease")
)


class LevelTesterWindow(tk.Toplevel):
    def __init__(self, master=None, initial_path: Optional[str] = None):
        super().__init__(master)
        self.title("BallDropParty Level Tester")
        self.geometry("1180x760")
        self.minsize(980, 620)

        default_path = initial_path or DEFAULT_TEST_FOLDER
        if not os.path.exists(default_path):
            default_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Levels"))

        self.path_var = tk.StringVar(value=default_path)
        self.budget_var = tk.DoubleVar(value=180.0)
        self.status_var = tk.StringVar(value="Ready")
        self.cancel_event = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self.result_queue: queue.Queue = queue.Queue()
        self.results: dict[str, SolveResult] = {}

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self._poll_results)

    def _build_ui(self) -> None:
        top = ttk.LabelFrame(self, text="Input", padding=8)
        top.pack(fill="x", padx=8, pady=(8, 4))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="File/Folder").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(top, textvariable=self.path_var).grid(row=0, column=1, sticky="ew", padx=(0, 6))
        ttk.Button(top, text="File", command=self.choose_file, width=8).grid(row=0, column=2, padx=2)
        ttk.Button(top, text="Folder", command=self.choose_folder, width=8).grid(row=0, column=3, padx=2)

        ttk.Label(top, text="Budget/level").grid(row=0, column=4, sticky="e", padx=(14, 4))
        ttk.Spinbox(top, from_=1, to=600, textvariable=self.budget_var, width=7, increment=10).grid(row=0, column=5)
        ttk.Label(top, text="sec").grid(row=0, column=6, sticky="w", padx=(4, 10))

        self.start_button = ttk.Button(top, text="Start", command=self.start_test, width=10)
        self.start_button.grid(row=0, column=7, padx=2)
        self.cancel_button = ttk.Button(top, text="Cancel", command=self.cancel_test, width=10, state="disabled")
        self.cancel_button.grid(row=0, column=8, padx=2)

        body = ttk.PanedWindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=8, pady=4)

        table_frame = ttk.Frame(body)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        body.add(table_frame, weight=4)

        columns = ("file", "status", "attempt", "time", "clicks", "steps", "nodes")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("file", text="File")
        self.tree.heading("status", text="Status")
        self.tree.heading("attempt", text="Attempt")
        self.tree.heading("time", text="Time")
        self.tree.heading("clicks", text="Clicks")
        self.tree.heading("steps", text="Steps")
        self.tree.heading("nodes", text="Nodes")
        self.tree.column("file", width=420)
        self.tree.column("status", width=95, anchor="center")
        self.tree.column("attempt", width=80, anchor="center")
        self.tree.column("time", width=85, anchor="center")
        self.tree.column("clicks", width=80, anchor="center")
        self.tree.column("steps", width=80, anchor="center")
        self.tree.column("nodes", width=90, anchor="center")
        self.tree.tag_configure("PASS", foreground="#047857")
        self.tree.tag_configure("FAIL", foreground="#B91C1C")
        self.tree.tag_configure("TIMEOUT", foreground="#92400E")
        self.tree.tag_configure("ERROR", foreground="#B91C1C")
        self.tree.tag_configure("CANCELLED", foreground="#4B5563")
        self.tree.tag_configure("PROCESSING", foreground="#1D4ED8")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.show_selected_result)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        detail_frame = ttk.LabelFrame(body, text="Solution path", padding=6)
        detail_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)
        body.add(detail_frame, weight=2)

        self.detail_text = tk.Text(detail_frame, height=9, wrap="word", font=("Consolas", 10))
        self.detail_text.grid(row=0, column=0, sticky="nsew")
        detail_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.grid(row=0, column=1, sticky="ns")

        bottom = ttk.Frame(self, padding=(8, 0, 8, 8))
        bottom.pack(fill="x")
        ttk.Label(bottom, textvariable=self.status_var).pack(side="left")

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose level JSON",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if path:
            self.path_var.set(path)

    def choose_folder(self) -> None:
        path = filedialog.askdirectory(title="Choose level folder")
        if path:
            self.path_var.set(path)

    def start_test(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        path = self.path_var.get().strip()
        files = iter_json_files(path)
        if not files:
            messagebox.showwarning("No JSON", "No JSON level files found.")
            return

        self.cancel_event.clear()
        self.results.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.detail_text.delete("1.0", "end")

        for file_path in files:
            self.tree.insert(
                "",
                "end",
                iid=file_path,
                values=(os.path.basename(file_path), "PENDING", "-", "-", "-", "-", "-"),
            )

        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status_var.set(f"Testing 0/{len(files)} files...")
        self.worker = threading.Thread(target=self._worker, args=(files, float(self.budget_var.get())), daemon=True)
        self.worker.start()

    def cancel_test(self) -> None:
        self.cancel_event.set()
        self.status_var.set("Cancelling...")

    def _worker(self, files: list[str], budget: float) -> None:
        completed = 0
        total = len(files)
        for file_path in files:
            if self.cancel_event.is_set():
                break
            self.result_queue.put(("processing", file_path, completed, total))
            started = time.monotonic()
            try:
                simulator = BallDropSimulator.from_file(file_path)
                solver = DeepSearchSolver(simulator, time_budget=budget)
                result = solver.solve_file(file_path, cancel_check=self.cancel_event.is_set)
            except Exception as exc:
                result = SolveResult(
                    file_path=file_path,
                    status="ERROR",
                    elapsed=time.monotonic() - started,
                    message=str(exc),
                )
            completed += 1
            self.result_queue.put(("result", result, completed, total))
        self.result_queue.put(("done", completed, total))

    def _poll_results(self) -> None:
        try:
            while True:
                item = self.result_queue.get_nowait()
                if item[0] == "result":
                    _, result, completed, total = item
                    self._apply_result(result)
                    self.status_var.set(f"Testing {completed}/{total} files...")
                elif item[0] == "processing":
                    _, file_path, completed, total = item
                    self._mark_processing(file_path)
                    self.status_var.set(f"Testing {completed}/{total} files...")
                elif item[0] == "done":
                    _, completed, total = item
                    self.start_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    if self.cancel_event.is_set():
                        self.status_var.set(f"Cancelled after {completed}/{total} files.")
                    else:
                        self.status_var.set(f"Done. Tested {completed}/{total} files.")
        except queue.Empty:
            pass
        self.after(100, self._poll_results)

    def _apply_result(self, result: SolveResult) -> None:
        self.results[result.file_path] = result
        status = result.status
        values = (
            os.path.basename(result.file_path),
            status,
            result.attempt or "-",
            f"{result.elapsed:.1f}s",
            result.clicks or len(result.solution) or "-",
            result.steps or "-",
            result.nodes or "-",
        )
        if self.tree.exists(result.file_path):
            self.tree.item(result.file_path, values=values, tags=(status,))
        else:
            self.tree.insert("", "end", iid=result.file_path, values=values, tags=(status,))
        self.tree.see(result.file_path)

    def _mark_processing(self, file_path: str) -> None:
        if not self.tree.exists(file_path):
            return
        self.tree.item(
            file_path,
            values=(os.path.basename(file_path), "PROCESSING", "-", "-", "-", "-", "-"),
            tags=("PROCESSING",),
        )
        self.tree.see(file_path)

    def show_selected_result(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        file_path = selected[0]
        result = self.results.get(file_path)
        self.detail_text.delete("1.0", "end")
        if not result:
            self.detail_text.insert("end", "No result yet.")
            return
        self.detail_text.insert("end", f"{result.status}: {file_path}\n")
        if result.message:
            self.detail_text.insert("end", f"{result.message}\n")
        if result.solution:
            self.detail_text.insert("end", "\n")
            for index, action in enumerate(result.solution, start=1):
                self.detail_text.insert("end", f"{index:03d}. {action.label()}\n")
        else:
            self.detail_text.insert("end", "\nNo solution path.")

    def close(self) -> None:
        self.cancel_event.set()
        self.destroy()


def open_level_tester(master=None, initial_path: Optional[str] = None) -> LevelTesterWindow:
    window = LevelTesterWindow(master=master, initial_path=initial_path)
    window.focus_set()
    return window

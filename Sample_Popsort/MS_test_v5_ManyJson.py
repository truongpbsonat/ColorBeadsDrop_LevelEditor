# -*- coding: utf-8 -*-
import json
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from collections import Counter, deque

# --- CORE SIMULATOR ---
class MS_Simulator_Core:
    def __init__(self):
        self.raw_data = None
        self.reset_state()

    def reset_state(self, data=None):
        if data: self.raw_data = data
        d = self.raw_data if self.raw_data else {}
        self.grid = [dict(c) for c in d.get("gridCells", [])]
        for c in self.grid:
            c["isWall"] = len(c.get("colorList", [])) == 0
            
        self.rows, self.cols = d.get("gridRows", 0), d.get("gridCols", 0)
        self.lanes = []
        lane_keys = sorted([k for k in d.keys() if "lane" in k.lower() and "Data" in k])
        for k in lane_keys:
            lane = [dict(item) for item in d[k]]
            for item in lane: item["prog"] = 0
            self.lanes.append(lane)
            
        self.conveyor = [None] * 40 
        self.hopper = []
        self.status = "PLAYING"
        self.update_visibility()

    def is_cell_passable(self, r, c):
        if 0 <= r < self.rows and 0 <= c < self.cols:
            idx = r * self.cols + c
            cell = self.grid[idx]
            if cell.get("isWall") or cell.get("colorList") or cell.get("isFrozen"):
                return False
            return True
        return False

    def has_path_to_exit(self, start_r, start_c):
        if start_r == 0: return True 
        queue = deque()
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = start_r + dr, start_c + dc
            if self.is_cell_passable(nr, nc): queue.append((nr, nc))
        visited = set(queue)
        while queue:
            r, c = queue.popleft()
            if r == 0: return True
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if (nr, nc) not in visited and self.is_cell_passable(nr, nc):
                    visited.add((nr, nc))
                    queue.append((nr, nc))
        return False

    def update_visibility(self):
        if not self.grid: return
        for r in range(self.rows):
            for c in range(self.cols):
                idx = r * self.cols + c
                cell = self.grid[idx]
                if cell.get("isWall"):
                    cell["isActive"] = False
                    continue
                has_marble = len(cell.get("colorList", [])) > 0
                if has_marble and not cell.get("isFrozen", False):
                    cell["isActive"] = self.has_path_to_exit(r, c)
                else:
                    cell["isActive"] = False

    def click_container(self, idx):
        cell = self.grid[idx]
        if cell.get("isActive") and cell.get("colorList"):
            color = cell["colorList"][0]
            for _ in range(9): self.hopper.append(color)
            cell["colorList"] = []
            self.update_visibility()

    def step(self):
        last = self.conveyor[-1]
        for i in range(39, 0, -1): self.conveyor[i] = self.conveyor[i-1]
        self.conveyor[0] = last

        if self.lanes:
            spacing = 40 // (len(self.lanes) + 1)
            for i, lane in enumerate(self.lanes):
                if not lane: continue
                pos = (i * spacing + 10) % 40
                if self.conveyor[pos] is not None and int(self.conveyor[pos]) == int(lane[0]["colorId"]):
                    lane[0]["prog"] += 1
                    self.conveyor[pos] = None
                    if lane[0]["prog"] >= 3:
                        lane.pop(0)
                        for c in self.grid:
                            if c.get("isFrozen") and c.get("frozenCount", 0) > 0:
                                c["frozenCount"] -= 1
                                if c["frozenCount"] <= 0: c["isFrozen"] = False
                        self.update_visibility()

        if self.hopper and self.conveyor[0] is None:
            self.conveyor[0] = self.hopper.pop(0)

        needed = [l[0]["colorId"] for l in self.lanes if l]
        is_full = all(s is not None for s in self.conveyor)
        match_exists = any(s in needed for s in self.conveyor if s is not None)
        
        if not self.hopper and not any(self.conveyor) and not any(self.lanes):
            self.status = "WIN"
        elif is_full and not match_exists and self.hopper:
            self.status = "LOSE"

# --- GUI ---
class BatchTesterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MS Tester - 3000 Steps & 3000 Attempts Mode")
        self.geometry("900x700")
        self.configure(bg="#ffffff")
        
        self.folder_path = tk.StringVar()
        self.is_running = False
        self.sim = MS_Simulator_Core()
        
        self.setup_ui()

    def setup_ui(self):
        header = tk.Frame(self, bg="#ffffff", pady=20)
        header.pack(fill="x")
        
        tk.Label(header, text="Folder Level:", bg="#ffffff", font=("Arial", 10)).pack(side="left", padx=10)
        tk.Entry(header, textvariable=self.folder_path, width=55).pack(side="left", padx=5)
        tk.Button(header, text="Chọn Thư Mục", command=self.select_folder).pack(side="left", padx=5)
        
        self.btn_start = tk.Button(header, text="BẮT ĐẦU TEST (3000x3000)", bg="#27ae60", fg="white", 
                                   padx=15, font=("Arial", 10, "bold"), command=self.start_test)
        self.btn_start.pack(side="right", padx=20)

        frame_table = tk.Frame(self, bg="#ffffff")
        frame_table.pack(fill="both", expand=True, padx=10)

        cols = ("file", "status", "attempts")
        self.tree = ttk.Treeview(frame_table, columns=cols, show="headings")
        self.tree.heading("file", text="Tên File JSON")
        self.tree.heading("status", text="Kết Quả")
        self.tree.heading("attempts", text="Số Lần Thử Đến Khi Thắng")
        
        self.tree.column("file", width=400)
        self.tree.column("status", width=120, anchor="center")
        self.tree.column("attempts", width=200, anchor="center")
        
        self.tree.tag_configure("pass", foreground="#27ae60", background="#f1f9f5")
        self.tree.tag_configure("fail", foreground="#e74c3c", background="#fdf2f2")
        
        scrollbar = ttk.Scrollbar(frame_table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.lbl_progress = tk.Label(self, text="Tiến độ: 0/0 file", bg="#ffffff")
        self.lbl_progress.pack(pady=5)
        self.progress = ttk.Progressbar(self, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=10)

    def select_folder(self):
        path = filedialog.askdirectory()
        if path: self.folder_path.set(path)

    def start_test(self):
        if not self.folder_path.get():
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn thư mục!")
            return
        if self.is_running: return
        
        self.is_running = True
        self.btn_start.config(state="disabled", text="Đang tính toán...")
        self.tree.delete(*self.tree.get_children())
        
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        folder = self.folder_path.get()
        files = sorted([f for f in os.listdir(folder) if f.endswith('.json')])
        self.progress["maximum"] = len(files)
        
        for i, filename in enumerate(files):
            try:
                with open(os.path.join(folder, filename), "r", encoding="utf-8") as f:
                    data = json.load(f)

                win_at = -1
                # NÂNG CẤP: Chạy đúng 3000 lần thử
                for att in range(1, 3001):
                    self.sim.reset_state(data)
                    steps = 0
                    # NÂNG CẤP: Chạy tối đa 3000 bước/ván
                    while self.sim.status == "PLAYING" and steps < 3000:
                        if len(self.sim.hopper) < 10:
                            demand = Counter([l[0]["colorId"] for l in self.sim.lanes if l])
                            cand = [(idx, demand.get(c["colorList"][0], 0)) 
                                    for idx, c in enumerate(self.sim.grid) if c.get("isActive")]
                            cand.sort(key=lambda x: x[1], reverse=True)
                            if cand: self.sim.click_container(cand[0][0])
                        self.sim.step()
                        steps += 1
                    
                    if self.sim.status == "WIN":
                        win_at = att
                        break
                
                self.after(0, self.update_row, filename, win_at, i+1, len(files))
                
            except Exception as e:
                self.after(0, self.update_row, filename, -2, i+1, len(files), str(e))

        self.is_running = False
        self.after(0, lambda: self.btn_start.config(state="normal", text="BẮT ĐẦU TEST (3000x3000)"))

    def update_row(self, filename, win_at, current, total, err_msg=""):
        if win_at > 0:
            self.tree.insert("", "end", values=(filename, "✅ PASS", f"{win_at} / 3000"), tags=("pass",))
        elif win_at == -1:
            self.tree.insert("", "end", values=(filename, "❌ FAIL", "KHÔNG THẮNG (3000+)"), tags=("fail",))
        else:
            self.tree.insert("", "end", values=(filename, "⚠️ ERROR", err_msg), tags=("fail",))
            
        self.tree.yview_moveto(1)
        self.progress["value"] = current
        self.lbl_progress.config(text=f"Tiến độ: {current}/{total} file")

if __name__ == "__main__":
    app = BatchTesterApp()
    app.mainloop()
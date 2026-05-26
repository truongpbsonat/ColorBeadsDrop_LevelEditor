# -*- coding: utf-8 -*-
import json, os, random
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# --- BẢNG MÀU CẬP NHẬT (THÊM ID 6) ---
VALUE_COLORS = {
    0: "#ef4444", 1: "#3b82f6", 2: "#22c55e", 
    3: "#facc15", 4: "#ec4899", 5: "#f97316", 
    6: "#9333ea", 24: "#212121"
}
COLOR_NAMES = {0: "Red", 1: "Blue", 2: "Green", 3: "Yellow", 4: "Pink", 5: "Orange", 6: "Purple"}

class MS_Editor_v2_0(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MS_Editor_v2.0 - Full Hotkeys & Purple ID")
        self.geometry("1500x900")
        
        self.level_data = {"gridCells": []}
        self.config_folder = tk.StringVar()
        self.export_folder = tk.StringVar()
        self.level_name_var = tk.StringVar(value="Level_Result")
        self.current_selected_path = None
        
        self.setup_ui()
        self.bind_global_hotkeys() # Gán phím tắt toàn cục

    def setup_ui(self):
        # TOPBAR
        top = ttk.Frame(self, padding=10); top.pack(fill="x")
        ttk.Label(top, text="Config:").pack(side="left")
        ttk.Entry(top, textvariable=self.config_folder, width=25).pack(side="left", padx=5)
        ttk.Button(top, text="📁", command=self.browse_config_folder).pack(side="left")
        
        tk.Button(top, text="🎲 RANDOM (R)", command=self.rerun_randomize, bg="#3498db", fg="white").pack(side="left", padx=15)
        
        ttk.Label(top, text="Export:").pack(side="left")
        ttk.Entry(top, textvariable=self.export_folder, width=25).pack(side="left", padx=5)
        ttk.Button(top, text="📂", command=self.browse_export_folder).pack(side="left")
        tk.Button(top, text="💾 EXPORT (E)", command=self.export_json, bg="#27ae60", fg="white", padx=15).pack(side="right", padx=10)

        # BODY
        body = ttk.Frame(self); body.pack(fill="both", expand=True, padx=10)
        
        # Listbox (Trái)
        left_f = ttk.LabelFrame(body, text=" Files (Up/Down) ")
        left_f.pack(side="left", fill="y", padx=(0, 10))
        self.file_listbox = tk.Listbox(left_f, width=30, font=("Consolas", 10), exportselection=False)
        self.file_listbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)

        # Grid Preview (Giữa)
        mid_grid = ttk.LabelFrame(body, text=" Grid Preview ")
        mid_grid.pack(side="left", fill="both", expand=True)
        self.grid_frame = tk.Frame(mid_grid); self.grid_frame.pack(expand=True)

        # Lane Preview (Phải)
        right_lane = ttk.LabelFrame(body, text=" Lane Data ")
        right_lane.pack(side="right", fill="y")
        self.lane_canvas = tk.Canvas(right_lane, bg="#2c3e50", width=200); self.lane_canvas.pack(fill="both", expand=True)

    def bind_global_hotkeys(self):
        # Bind vào 'self' thay vì listbox để nhận lệnh mọi lúc
        self.bind("<Up>", self.navigate_list)
        self.bind("<Down>", self.navigate_list)
        self.bind("<r>", lambda e: self.rerun_randomize())
        self.bind("<R>", lambda e: self.rerun_randomize())
        self.bind("<e>", lambda e: self.export_json())
        self.bind("<E>", lambda e: self.export_json())

    def navigate_list(self, event):
        """Xử lý di chuyển lên xuống trong danh sách không cần focus"""
        current_sel = self.file_listbox.curselection()
        if not current_sel:
            index = 0
        else:
            index = current_sel[0]
            if event.keysym == "Up": index = max(0, index - 1)
            elif event.keysym == "Down": index = min(self.file_listbox.size() - 1, index + 1)
        
        self.file_listbox.selection_clear(0, tk.END)
        self.file_listbox.selection_set(index)
        self.file_listbox.see(index)
        self.on_file_select(None)

    def browse_config_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.config_folder.set(d)
            self.refresh_file_list()

    def browse_export_folder(self):
        d = filedialog.askdirectory()
        if d: self.export_folder.set(d)

    def refresh_file_list(self):
        folder = self.config_folder.get()
        self.file_listbox.delete(0, tk.END)
        if not os.path.exists(folder): return
        files = sorted([f for f in os.listdir(folder) if f.endswith('.json')])
        for f in files: self.file_listbox.insert(tk.END, f)
        if files:
            self.file_listbox.selection_set(0)
            self.on_file_select(None)

    def on_file_select(self, event):
        selection = self.file_listbox.curselection()
        if not selection: return
        filename = self.file_listbox.get(selection[0])
        self.current_selected_path = os.path.join(self.config_folder.get(), filename)
        self.gen_level_logic(self.current_selected_path)

    def rerun_randomize(self):
        if self.current_selected_path: self.gen_level_logic(self.current_selected_path)

    def gen_level_logic(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                c = json.load(f)
            
            # Đọc thông số và ép kiểu
            r, col = int(c.get('Row', 5)), int(c.get('Col', 5))
            num_cont, num_wall = int(c.get('Container', 0)), int(c.get('Wall', 0))
            num_lane, u_color = int(c.get('Lane', 4)), int(c.get('uniqueColor', 3))
            h_count, f_count = int(c.get('hidden', 0)), int(c.get('frozen', 0))
            lvl_id = c.get('Level', "New")
            self.level_name_var.set(f"Level_{lvl_id}")

            # Khởi tạo data Grid
            self.level_data = {
                "levelName": f"Level_{lvl_id}", "gridRows": r, "gridCols": col,
                "gridCells": [{"isActive": False, "colorList": [], "isHidden": False, "unlockDirection": 0, "isTunnel": False, "isFrozen": False, "frozenCount": 0} for _ in range(r*col)]
            }

            # Rải vật thể ngẫu nhiên
            indices = list(range(r * col)); random.shuffle(indices)
            for _ in range(min(num_wall, len(indices))): indices.pop()
            cont_indices = [indices.pop() for _ in range(min(num_cont, len(indices)))]

            for i, idx in enumerate(cont_indices):
                cid = random.randint(0, u_color - 1)
                is_h = (i < h_count)
                is_f = (not is_h and i < (h_count + f_count))
                self.level_data["gridCells"][idx].update({
                    "colorList": [cid], "isHidden": is_h, "isFrozen": is_f, "frozenCount": 5 if is_f else 0
                })

            # Chia Lane Data
            pool = []
            for cell in self.level_data["gridCells"]:
                if cell["colorList"]:
                    for _ in range(3): pool.append({"colorId": cell["colorList"][0], "type": 0})
            random.shuffle(pool)
            for i, item in enumerate(pool):
                lk = f"lane{(i % num_lane) + 1}Data"
                if lk not in self.level_data: self.level_data[lk] = []
                self.level_data[lk].append(item)

            self.refresh_ui_display(r, col, num_lane)
        except Exception as e: print(f"Gen Error: {e}")

    def refresh_ui_display(self, r, col, num_lane):
        for w in self.grid_frame.winfo_children(): w.destroy()
        for ri in range(r):
            for ci in range(col):
                idx = ri * col + ci
                cell = self.level_data["gridCells"][idx]
                cell["isActive"] = (ri == 0) and (len(cell["colorList"]) > 0)
                
                btn = tk.Button(self.grid_frame, width=8, height=3, relief="groove")
                btn.grid(row=(r-1)-ri, column=ci, padx=1, pady=1)
                
                clist = cell["colorList"]
                if not clist:
                    btn.config(text="WALL", bg="#333", fg="gray")
                else:
                    cid = clist[0]
                    txt = f"{COLOR_NAMES[cid]}"
                    if cell["isHidden"]: txt += "\n[H]"
                    if cell["isFrozen"]: txt += f"\n❄️{cell['frozenCount']}"
                    btn.config(text=txt, bg=VALUE_COLORS[cid], fg="black" if cell["isActive"] else "#555")

        self.lane_canvas.delete("all")
        for i in range(1, num_lane + 1):
            data = self.level_data.get(f"lane{i}Data", [])
            for j, item in enumerate(data):
                x, y = 10 + (i-1)*42, 10 + j*22
                self.lane_canvas.create_rectangle(x, y, x+32, y+18, fill=VALUE_COLORS[item["colorId"]], outline="white")

    def export_json(self):
        folder = self.export_folder.get()
        if not folder: return
        p = os.path.join(folder, f"{self.level_name_var.get()}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.level_data, f, indent=4)
        print(f"✔️ Exported: {p}")

if __name__ == "__main__":
    MS_Editor_v2_0().mainloop()
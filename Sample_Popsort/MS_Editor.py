# -*- coding: utf-8 -*-
import json, os, random, re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from collections import Counter

# --- CẤU HÌNH MÀU SẮC ---
VALUE_COLORS = {
    0: "#ef4444", 1: "#3b82f6", 2: "#22c55e", 
    3: "#facc15", 4: "#ec4899", 5: "#f97316", 
    6: "#9333ea", 24: "#212121"
}
COLOR_NAMES = {0: "Red", 1: "Blue", 2: "Green", 3: "Yellow", 4: "Pink", 5: "Orange", 6: "Purple"}

def get_lane_number(key):
    nums = re.findall(r'\d+', key)
    return int(nums[0]) if nums else 0

class MS_Editor_Final_Complete(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MS_Editor_v2.0 PRO - Stable & Ordered")
        self.geometry("1600x950")
        
        self.level_data = {}
        self.rows_var = tk.StringVar(value="3")
        self.cols_var = tk.StringVar(value="3")
        self.level_name_var = tk.StringVar(value="Level_1")
        self.board_var = tk.IntVar(value=0)
        self.export_path = tk.StringVar()
        self.lane_count_var = tk.StringVar(value="3")
        
        self.edit_mode = tk.StringVar(value="EDIT") 
        self.switch_source = None 
        
        self.sel_grid_type = tk.IntVar(value=2) 
        self.sel_grid_color = tk.IntVar(value=0)
        self.sel_is_hidden = tk.BooleanVar(value=False)
        
        self.file_list = []
        self.lane_rects = []
        self.buttons = []
        
        self.setup_ui()
        self.bind_keys()

    def setup_ui(self):
        top_bar = ttk.Frame(self, padding=5); top_bar.pack(fill="x")
        ttk.Label(top_bar, text="Folder:").pack(side="left")
        ttk.Entry(top_bar, textvariable=self.export_path, width=30).pack(side="left", padx=5)
        ttk.Button(top_bar, text="📂 Browse", command=self.browse_folder).pack(side="left")
        ttk.Label(top_bar, text=" Rows:").pack(side="left", padx=(10, 0))
        ttk.Entry(top_bar, textvariable=self.rows_var, width=3).pack(side="left")
        ttk.Label(top_bar, text=" Cols:").pack(side="left", padx=(5, 0))
        ttk.Entry(top_bar, textvariable=self.cols_var, width=3).pack(side="left")
        ttk.Button(top_bar, text="🆕 NEW (N)", command=self.new_level).pack(side="left", padx=10)
        
        self.btn_mode = tk.Button(top_bar, textvariable=self.edit_mode, width=15, font=("Arial", 10, "bold"), 
                                  bg="#3498db", fg="white", command=self.toggle_mode)
        self.btn_mode.pack(side="left", padx=20)
        
        ttk.Button(top_bar, text="🎲 RANDOM (R)", command=self.random_cargo).pack(side="right", padx=5)
        ttk.Button(top_bar, text="🔍 CHECK (V)", command=self.check_logic).pack(side="right", padx=5)
        ttk.Button(top_bar, text="💾 EXPORT (E)", command=self.export_json).pack(side="right", padx=5)
        
        body = ttk.Frame(self); body.pack(fill="both", expand=True, padx=10)
        
        # Danh sách file bên trái
        self.nav_frame = ttk.LabelFrame(body, text="File List (Sorted)", width=220)
        self.nav_frame.pack(side="left", fill="y", padx=(0, 10))
        self.listbox = tk.Listbox(self.nav_frame, font=("Arial", 10))
        self.listbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        
        # Grid thiết kế ở giữa
        mid_frame = ttk.LabelFrame(body, text="Grid Design"); mid_frame.pack(side="left", fill="both", expand=True)
        self.grid_frame = tk.Frame(mid_frame); self.grid_frame.pack(fill="both", expand=True)

        # KHỞI TẠO FRAME BÊN PHẢI TRƯỚC
        right = ttk.Frame(body, width=320); right.pack(side="right", fill="y", padx=10)
        
        li = ttk.LabelFrame(right, text="Level Info"); li.pack(fill="x", pady=5)
        ttk.Label(li, text="Name:").pack()
        ttk.Entry(li, textvariable=self.level_name_var).pack(fill="x", padx=5, pady=2)
        
        lane_ctrl = ttk.LabelFrame(right, text="3. Lane Config"); lane_ctrl.pack(fill="x", pady=5)
        ttk.Label(lane_ctrl, text="Number of Lanes:").pack(side="left", padx=5)
        ttk.Entry(lane_ctrl, textvariable=self.lane_count_var, width=5).pack(side="left", padx=5)
        
        b_frame = ttk.Frame(li); b_frame.pack(fill="x", pady=5)
        ttk.Label(b_frame, text="Board Type:").pack(side="left", padx=5)
        for b_val in [0, 1, 2]:
            tk.Radiobutton(b_frame, text=str(b_val), variable=self.board_var, value=b_val).pack(side="left")
        
        g_ctrl = ttk.LabelFrame(right, text="1. Tool Mode"); g_ctrl.pack(fill="x", pady=5)
        for l, v in [("Normal", 2), ("Tunnel", 4), ("WALL", 0)]:
            tk.Radiobutton(g_ctrl, text=l, variable=self.sel_grid_type, value=v, indicatoron=0, width=9).pack(side="left", padx=2, pady=5)
        tk.Checkbutton(right, text="Is Hidden (H)", variable=self.sel_is_hidden, font=("Arial", 10, "bold")).pack(fill="x")
        
        p2 = ttk.LabelFrame(right, text="2. Palette"); p2.pack(fill="x", pady=5)
        for i in range(7):
            tk.Radiobutton(p2, text=COLOR_NAMES[i], variable=self.sel_grid_color, value=i, indicatoron=0, width=10, bg=VALUE_COLORS[i]).grid(row=i//2, column=i%2, padx=5, pady=5)

        self.lane_lab = ttk.LabelFrame(right, text="Lane Preview"); self.lane_lab.pack(fill="both", expand=True)
        lane_container = tk.Frame(self.lane_lab)
        lane_container.pack(fill="both", expand=True)

        self.lane_canvas = tk.Canvas(lane_container, bg="#1a1a1a", highlightthickness=0)
        self.lane_vbar = tk.Scrollbar(lane_container, orient="vertical", command=self.lane_canvas.yview)
        self.lane_canvas.configure(yscrollcommand=self.lane_vbar.set)
        self.lane_vbar.pack(side="right", fill="y")
        self.lane_canvas.pack(side="left", fill="both", expand=True)
        self.lane_canvas.bind("<Button-1>", self.on_lane_click)
    def new_level(self):
        try:
            r = int(self.rows_var.get())
            c = int(self.cols_var.get())
        except:
            messagebox.showerror("Error", "Rows và Cols phải là số nguyên!")
            return

        if r <= 0 or c <= 0:
            messagebox.showerror("Error", "Kích thước không hợp lệ!")
            return

        # Khởi tạo lại level_data
        self.row, self.col = r, c
        self.level_data = {
            "levelName": self.level_name_var.get(),
            "board": self.board_var.get(),
            "gridRows": r,
            "gridCols": c,
            "gridCells": []
        }

        # Tạo danh sách ô trống (WALL)
        for _ in range(r * c):
            self.level_data["gridCells"].append({
                "isActive": False,
                "colorList": [],
                "isHidden": False,
                "isTunnel": False,
                "isFrozen": False
            })

        # Xóa các lane cũ nếu có
        keys_to_del = [k for k in self.level_data.keys() if k.startswith("lane")]
        for k in keys_to_del: del self.level_data[k]

        # Cập nhật giao diện
        self.build_grid()
        self.apply_logic_and_refresh()
        messagebox.showinfo("New Level", f"Đã tạo lưới mới {r}x{c}!")

    def bind_keys(self):
        self.bind("[", lambda e: self.move_file_selection(-1))
        self.bind("]", lambda e: self.move_file_selection(1))
        self.bind("v", lambda e: self.check_logic()); self.bind("V", lambda e: self.check_logic())
        self.bind("r", lambda e: self.random_cargo()); self.bind("R", lambda e: self.random_cargo())
        self.bind("s", lambda e: self.toggle_mode()); self.bind("S", lambda e: self.toggle_mode())
        self.bind("e", lambda e: self.export_json()); self.bind("E", lambda e: self.export_json())
        self.bind("h", self.toggle_hidden_at_mouse)
        self.bind("H", self.toggle_hidden_at_mouse)

    def clear_cell(self, idx):
        # Reset ô về trạng thái mặc định (trống)
        if idx < len(self.level_data["gridCells"]):
            self.level_data["gridCells"][idx].update({
                "isActive": False,
                "colorList": [],
                "isHidden": False,
                "isTunnel": False,
                "isFrozen": False,
                "frozenCount": 0
            })
            self.apply_logic_and_refresh()    

    def toggle_mode(self):
        self.edit_mode.set("SWITCH" if self.edit_mode.get() == "EDIT" else "EDIT")
        self.btn_mode.config(bg="#e74c3c" if self.edit_mode.get() == "SWITCH" else "#3498db")
        self.switch_source = None
        self.refresh_ui()
    def toggle_hidden_at_mouse(self, event=None):
        # Đảo trạng thái của biến checkbox trên giao diện
        new_val = not self.sel_is_hidden.get()
        self.sel_is_hidden.set(new_val)
        
        # Tìm ô dưới chuột để áp dụng trực tiếp
        x, y = self.winfo_pointerxy()
        widget = self.winfo_containing(x, y)
        for r in range(self.row):
            for c in range(self.col):
                if self.buttons[r][c] == widget:
                    idx = r * self.col + c
                    self.level_data["gridCells"][idx]["isHidden"] = new_val
                    self.apply_logic_and_refresh()
                    break

    def on_left_click(self, idx):
        if self.edit_mode.get() == "SWITCH":
            if self.switch_source and self.switch_source['type'] == 'grid':
                ia, ib = self.switch_source['idx'], idx
                self.level_data["gridCells"][ia], self.level_data["gridCells"][ib] = self.level_data["gridCells"][ib], self.level_data["gridCells"][ia]
                self.switch_source = None; self.apply_logic_and_refresh()
            else:
                self.switch_source = {'type': 'grid', 'idx': idx}; self.refresh_ui()
        else: self.handle_edit_logic(idx)

    def on_lane_click(self, event):
        if self.edit_mode.get() != "SWITCH": return
        canvas_y = self.lane_canvas.canvasy(event.y)
        for item in self.lane_rects:
            x1, y1, x2, y2 = item['coords']
            if x1 <= event.x <= x2 and y1 <= canvas_y <= y2:
                if self.switch_source and self.switch_source['type'] == 'lane':
                    la, ia = self.switch_source['lane'], self.switch_source['idx']
                    lb, ib = item['lane'], item['idx']
                    self.level_data[f"lane{la}Data"][ia], self.level_data[f"lane{lb}Data"][ib] = \
                    self.level_data[f"lane{lb}Data"][ib], self.level_data[f"lane{la}Data"][ia]
                    self.switch_source = None; self.draw_lanes()
                else:
                    self.switch_source = {'type': 'lane', 'lane': item['lane'], 'idx': item['idx']}; self.draw_lanes()
                break

    def random_cargo(self):
        if not self.level_data: return
        pool = []
        for cell in self.level_data["gridCells"]:
            for c in cell.get("colorList", []):
                if c >= 0: [pool.append({"colorId": c, "type": 0}) for _ in range(3)]
        if not pool: return
        random.shuffle(pool)

        old_keys = [k for k in self.level_data.keys() if k.startswith("lane") and k.endswith("Data")]
        for k in old_keys: del self.level_data[k]

        try: num_lanes = int(self.lane_count_var.get())
        except: num_lanes = 3
            
        for i in range(1, num_lanes + 1):
            self.level_data[f"lane{i}Data"] = []
            
        for idx, item in enumerate(pool):
            lane_key = f"lane{(idx % num_lanes) + 1}Data"
            self.level_data[lane_key].append(item)

        self.draw_lanes()
        messagebox.showinfo("Random", f"✅ Shuffle Done with {num_lanes} lanes!")

    def check_logic(self):
        if not self.level_data: return
        grid_c = Counter()
        for cell in self.level_data["gridCells"]:
            for c in cell.get("colorList", []): grid_c[c] += 3
        lane_c = Counter()
        lk = [k for k in self.level_data.keys() if k.startswith("lane") and k.endswith("Data")]
        for k in lk:
            for item in self.level_data.get(k, []): lane_c[item["colorId"]] += 1
        if all(lane_c[clr] == grid_c[clr] for clr in grid_c): messagebox.showinfo("Check", "✅ OK!")
        else: messagebox.showwarning("Check", "❌ Color Mismatch!")

    def handle_edit_logic(self, idx):
        cell = self.level_data["gridCells"][idx]
        m, clr = self.sel_grid_type.get(), self.sel_grid_color.get()
        if m == 0: cell.update({"isActive": False, "colorList": [], "isHidden": False, "isTunnel": False, "isFrozen": False})
        elif m == 4: cell.update({"isTunnel": True, "colorList": [clr], "unlockDirection": 1, "isFrozen": False, "isHidden": False})
        else:
            if self.sel_is_hidden.get(): cell.update({"isTunnel": False, "colorList": [clr], "isHidden": True, "isFrozen": False})
            else:
                if not cell["isTunnel"] and cell["colorList"] == [clr] and not cell["isHidden"]:
                    cell["isFrozen"] = True; cell.setdefault("frozenCount", 0); cell["frozenCount"] += 1
                else: cell.update({"isTunnel": False, "colorList": [clr], "isHidden": False, "isFrozen": False, "frozenCount": 0})
        self.apply_logic_and_refresh()

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path: self.export_path.set(path); self.refresh_file_list()

    def refresh_file_list(self):
        p = self.export_path.get()
        if not p: return
        self.listbox.delete(0, tk.END)
        raw_files = [f for f in os.listdir(p) if f.endswith('.json')]
        self.file_list = sorted(raw_files, key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split('([0-9]+)', s)])
        for f in self.file_list: self.listbox.insert(tk.END, f)

    def on_listbox_select(self, event):
        sel = self.listbox.curselection()
        if not sel: return
        
        # 1. Lấy tên file từ danh sách (ví dụ: "10.json")
        full_file_name = self.listbox.get(sel[0])
        path = os.path.join(self.export_path.get(), full_file_name)
        
        # 2. Đọc dữ liệu JSON
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.level_data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Could not read file: {e}")
            return
            
        # 3. Trích xuất CHỈ SỐ từ tên file để đưa vào ô Level Name
        # Dùng regex để lấy số, ví dụ "10.json" -> "10"
        only_number = re.findall(r'\d+', full_file_name)
        level_id = only_number[0] if only_number else "1"
        self.level_name_var.set(level_id)
        
        # 4. Cập nhật các thông số khác lên giao diện
        self.row = self.level_data.get("gridRows", 3)
        self.col = self.level_data.get("gridCols", 3)
        self.board_var.set(self.level_data.get("board", 0)) 
        
        # 5. Vẽ lại Grid và Lane
        self.build_grid()
        self.apply_logic_and_refresh()

    def build_grid(self):
        for w in self.grid_frame.winfo_children(): w.destroy()
        self.buttons = []
        for r in range(self.row):
            row_btns = []
            for c in range(self.col):
                btn = tk.Button(self.grid_frame, width=12, height=4)
                # Tính toán index dựa trên cách bạn đang sắp xếp (hàng ngược từ dưới lên)
                idx = (r * self.col + c)
                
                btn.grid(row=(self.row-1)-r, column=c, padx=2, pady=2)
                
                # Chuột trái: Sửa/Đổi chỗ
                btn.bind("<Button-1>", lambda e, i=idx: self.on_left_click(i))
                
                # CHUỘT PHẢI: Xóa dữ liệu ô (Dùng Button-3 cho Windows/Linux)
                btn.bind("<Button-3>", lambda e, i=idx: self.clear_cell(i))
                # Hỗ trợ thêm cho macOS nếu dùng chuột Apple
                btn.bind("<Button-2>", lambda e, i=idx: self.clear_cell(i))
                
                row_btns.append(btn)
            self.buttons.append(row_btns)

    def apply_logic_and_refresh(self):
        for i, cell in enumerate(self.level_data["gridCells"]):
            cell["isActive"] = (i // self.col == 0) and (len(cell.get("colorList", [])) > 0)
        self.refresh_ui()

    def refresh_ui(self):
        for i, cell in enumerate(self.level_data["gridCells"]):
            btn = self.buttons[i // self.col][i % self.col]
            cl = cell.get("colorList", [])
            sel = self.switch_source and self.switch_source.get('type') == 'grid' and self.switch_source.get('idx') == i
            btn.config(highlightthickness=4 if sel else 0, highlightbackground="yellow")
            
            if cell.get("isTunnel"): 
                btn.config(text=f"TUNNEL\n{cl}", bg="#e67e22", fg="white")
            elif not cl: 
                btn.config(text="WALL", bg="#333", fg="#555")
            else:
                c_id = cl[0]
                txt = f"{COLOR_NAMES.get(c_id, 'ID '+str(c_id))}"
                if cell.get("isHidden"): txt += "\n(HIDDEN)"
                if cell.get("isFrozen"): txt += f"\n❄️ [{cell.get('frozenCount', 0)}]"
                btn.config(text=txt, bg=VALUE_COLORS.get(c_id, "#fff"), fg="black" if cell.get("isActive") else "#fff")
        self.draw_lanes()

    def draw_lanes(self):
        self.lane_canvas.delete("all"); self.lane_rects = []
        lane_keys = [k for k in self.level_data.keys() if k.startswith("lane") and k.endswith("Data")]
        lk = sorted(lane_keys, key=get_lane_number)
        
        for i, k in enumerate(lk):
            d = self.level_data.get(k, [])
            x = 20 + i * 65
            lane_num = get_lane_number(k)
            for j, item in enumerate(d):
                y = 20 + j * 30
                sel = self.switch_source and self.switch_source.get('type') == 'lane' and self.switch_source.get('lane') == lane_num and self.switch_source.get('idx') == j
                self.lane_canvas.create_rectangle(x, y, x+45, y+25, fill=VALUE_COLORS.get(item["colorId"], "#000"), outline="yellow" if sel else "white", width=3 if sel else 1)
                self.lane_rects.append({'lane': lane_num, 'idx': j, 'coords': (x, y, x+45, y+25)})
        self.lane_canvas.configure(scrollregion=self.lane_canvas.bbox("all"))

    def move_file_selection(self, delta):
        cur = self.listbox.curselection()
        if not cur: return
        idx = max(0, min(len(self.file_list)-1, cur[0]+delta))
        self.listbox.selection_clear(0, tk.END); self.listbox.selection_set(idx); self.on_listbox_select(None)

    def export_json(self):
        folder = self.export_path.get()
        if not folder:
            messagebox.showwarning("Warning", "Vui lòng chọn thư mục (Browse) trước!")
            return

        # 1. Định nghĩa file_name (Chỉ lấy số)
        raw_val = self.level_name_var.get()
        nums = re.findall(r'\d+', raw_val)
        file_name = nums[0] if nums else "1"
        
        # --- THÊM MỚI: KIỂM TRA TRÙNG TÊN ---
        path = os.path.join(folder, f"{file_name}.json")
        if os.path.exists(path):
            # Hiển thị thông báo Yes/No
            confirm = messagebox.askyesno(
                "Xác nhận ghi đè", 
                f"Level {file_name}.json đã tồn tại.\nBạn có muốn ghi đè lên file cũ không?"
            )
            if not confirm:
                return # Dừng hàm nếu chọn No
        # ------------------------------------

        # 2. Xây dựng cấu trúc dữ liệu xuất ra
        ordered_data = {
            "levelName": file_name,
            "board": self.board_var.get(),
            "gridRows": self.level_data.get("gridRows", 3),
            "gridCols": self.level_data.get("gridCols", 3),
            "gridCells": self.level_data.get("gridCells", [])
        }

        # 3. Quét và đưa các LaneData vào
        lane_keys = [k for k in self.level_data.keys() if k.startswith("lane") and k.endswith("Data")]
        lk_sorted = sorted(lane_keys, key=get_lane_number)
        for lk in lk_sorted:
            ordered_data[lk] = self.level_data[lk]

        # 4. Thực hiện ghi file
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(ordered_data, f, indent=4)
            
            messagebox.showinfo("Export Success", f"Đã lưu file: {file_name}.json")
            self.refresh_file_list()
        except Exception as e:
            messagebox.showerror("Export Error", f"Không thể lưu file: {e}")

if __name__ == "__main__":
    MS_Editor_Final_Complete().mainloop()
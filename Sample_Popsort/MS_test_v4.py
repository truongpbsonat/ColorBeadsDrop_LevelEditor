# -*- coding: utf-8 -*-
import pygame
import json
import sys
import math
from tkinter import filedialog, Tk
from collections import Counter, deque

# --- CẤU HÌNH ---
WIDTH, HEIGHT = 1350, 920
FPS = 120
COLORS = {
    0: (239, 68, 68),   # Red
    1: (59, 130, 246),  # Blue
    2: (34, 197, 94),   # Green
    3: (250, 204, 21),  # Yellow
    4: (236, 72, 153),  # Pink
    5: (249, 115, 22),  # Orange
    6: (147, 51, 234),  # Purple (ID 6 Mới thêm)
    7: (75, 85, 99),    # Gray (ID cũ được đẩy lên)
    "WALL": (30, 30, 35), "ICE": (150, 220, 255), "BG": (18, 18, 20),
    "PANEL": (28, 28, 30), "BTN": (60, 60, 65)
}

class MS_Simulator:
    def __init__(self):
        self.raw_data = None
        self.reset_data()

    def reset_data(self, data=None):
        if data: self.raw_data = data
        d = self.raw_data if self.raw_data else {}
        self.grid = []
        cells = d.get("gridCells", [])
        for c in cells:
            cell_dict = dict(c)
            # Ô trống lúc bắt đầu game = Wall chặn vĩnh viễn
            cell_dict["isWall"] = len(cell_dict.get("colorList", [])) == 0
            self.grid.append(cell_dict)
            
        self.rows, self.cols = d.get("gridRows", 0), d.get("gridCols", 0)
        self.lanes = []
        lane_keys = sorted([k for k in d.keys() if "lane" in k.lower() and "Data" in k])
        for k in lane_keys:
            lane = [dict(c) for c in d[k]]
            for c in lane: c["prog"] = 0
            self.lanes.append(lane)
            
        self.conveyor = [None] * 40 
        self.hopper = []
        self.status = "READY" if d else "IDLE"
        self.update_visibility()

    def is_cell_passable(self, r, c):
        if 0 <= r < self.rows and 0 <= c < self.cols:
            idx = r * self.cols + c
            cell = self.grid[idx]
            # Chỉ đi xuyên qua được nếu: Không phải Wall, Không có Marble, Không bị Frozen
            if cell.get("isWall") or cell.get("colorList") or cell.get("isFrozen"):
                return False
            return True
        return False

    def has_path_to_exit(self, start_r, start_c):
        if start_r == 0: return True 
        queue = deque()
        # Tìm đường thoát 4 hướng
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
            for _ in range(9): self.hopper.append(cell["colorList"][0])
            cell["colorList"] = []
            self.update_visibility()

    def step(self):
        if not self.grid: return
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

        # CẬP NHẬT TRẠNG THÁI (WIN / LOSE / PLAYING)
        needed = [l[0]["colorId"] for l in self.lanes if l]
        is_full = all(s is not None for s in self.conveyor)
        match_exists = any(s in needed for s in self.conveyor if s is not None)
        
        if not self.hopper and not any(self.conveyor) and not any(self.lanes):
            self.status = "LEVEL COMPLETE (WIN)"
        elif is_full and not match_exists and self.hopper:
            self.status = "LEVEL FAILED (LOSE)" 
        else:
            self.status = "PLAYING"

class App:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("MS Simulator - Purple ID Support")
        self.sim = MS_Simulator()
        self.font = pygame.font.SysFont("Arial", 20, bold=True)
        self.font_status = pygame.font.SysFont("Arial", 30, bold=True)
        self.speed_val, self.dragging, self.paused = 0.7, False, False
        self.last_tick, self.last_bot = 0, 0
        self.btns = {"import": pygame.Rect(1030, 50, 290, 60), "pause": pygame.Rect(1030, 130, 290, 60), "reset": pygame.Rect(1030, 210, 290, 60)}

    def render(self):
        self.screen.fill(COLORS["BG"])
        pygame.draw.rect(self.screen, COLORS["PANEL"], (1000, 0, 350, HEIGHT))
        
        # Vẽ Grid
        start_x = (1000 - self.sim.cols*90)//2
        for r in range(self.sim.rows):
            for c in range(self.sim.cols):
                idx = r*self.sim.cols + c
                if idx < len(self.sim.grid):
                    cell = self.sim.grid[idx]
                    rect = pygame.Rect(start_x+c*90, 40+(self.sim.rows-1-r)*75, 80, 65)
                    if cell.get("isWall"): col = COLORS["WALL"]
                    else:
                        cid = cell["colorList"][0] if cell.get("colorList") else None
                        if cid is not None:
                            col = COLORS.get(cid, (100,100,100))
                            if not cell.get("isActive"): col = tuple(max(20, x-140) for x in col)
                        else: col = (45, 45, 50)
                    pygame.draw.rect(self.screen, col, rect, 0, 10)
                    if cell.get("isFrozen"):
                        pygame.draw.rect(self.screen, COLORS["ICE"], rect, 4, 10)
                        txt = self.font.render(str(cell.get("frozenCount", 0)), True, COLORS["ICE"])
                        self.screen.blit(txt, (rect.centerx-10, rect.centery-10))
                    if cell.get("isActive"): pygame.draw.rect(self.screen, (255,255,255), rect, 3, 10)

        # Conveyor & UI
        cx, cy, rx, ry = 515, 620, 460, 85
        pygame.draw.ellipse(self.screen, (40, 40, 45), (cx-rx-25, cy-ry-25, rx*2+50, ry*2+50), 20)
        for i, val in enumerate(self.sim.conveyor):
            angle = (i/40)*2*math.pi
            px, py = cx + rx*math.cos(angle), cy + ry*math.sin(angle)
            if val is not None: pygame.draw.circle(self.screen, COLORS.get(val, (128,128,128)), (int(px), int(py)), 15)

        for i, lane in enumerate(self.sim.lanes):
            for j, cargo in enumerate(lane[:4]):
                r = pygame.Rect(60+i*115, 740+j*42, 100, 38)
                pygame.draw.rect(self.screen, COLORS.get(cargo["colorId"], (128,128,128)), r, 0, 8)
                if j == 0: self.screen.blit(self.font.render(f"{cargo['prog']}/3", True, (255,255,255)), (r.x+30, r.y+6))

        for k, r in self.btns.items():
            pygame.draw.rect(self.screen, COLORS["BTN"], r, 0, 10)
            t = self.font.render(k.upper(), True, (255,255,255))
            self.screen.blit(t, (r.centerx-t.get_width()//2, r.centery-t.get_height()//2))

        # HIỂN THỊ THÔNG BÁO TRẠNG THÁI
        msg = self.sim.status
        msg_col = (255, 255, 255)
        if "WIN" in msg: msg_col = (0, 255, 0)
        if "LOSE" in msg: msg_col = (255, 50, 50)
        
        txt_surface = self.font_status.render(msg, True, msg_col)
        self.screen.blit(txt_surface, (1030, 450))

        # Thanh trượt Speed
        pygame.draw.rect(self.screen, (70,70,75), (1030, 840, 280, 10))
        pygame.draw.circle(self.screen, (255,255,255), (int(1030 + self.speed_val*280), 845), 15)
        pygame.display.flip()

    def run(self):
        while True:
            m_pos = pygame.mouse.get_pos()
            for e in pygame.event.get():
                if e.type == pygame.QUIT: pygame.quit(); sys.exit()
                if e.type == pygame.MOUSEBUTTONDOWN:
                    if self.btns["import"].collidepoint(m_pos):
                        Tk().withdraw(); p = filedialog.askopenfilename()
                        if p: 
                            with open(p, "r", encoding="utf-8") as f:
                                self.sim.reset_data(json.load(f))
                    if self.btns["pause"].collidepoint(m_pos): self.paused = not self.paused
                    if self.btns["reset"].collidepoint(m_pos): self.sim.reset_data()
                    if pygame.Rect(1030, 820, 280, 50).collidepoint(m_pos): self.dragging = True
                if e.type == pygame.MOUSEBUTTONUP: self.dragging = False

            if self.dragging: self.speed_val = max(0, min(1, (m_pos[0]-1030)/280))
            if not self.paused and "WIN" not in self.sim.status and "LOSE" not in self.sim.status:
                now = pygame.time.get_ticks()
                if now - self.last_tick > int( (1.0-self.speed_val)*100):
                    self.sim.step(); self.last_tick = now
                if now - self.last_bot > 800 and len(self.sim.hopper) < 10:
                    demand = Counter([l[0]["colorId"] for l in self.sim.lanes if l])
                    cand = [(i, demand.get(c["colorList"][0], 0)) for i, c in enumerate(self.sim.grid) if c.get("isActive")]
                    cand.sort(key=lambda x: x[1], reverse=True)
                    if cand: self.sim.click_container(cand[0][0]); self.last_bot = now
            self.render(); pygame.time.Clock().tick(FPS)

if __name__ == "__main__": App().run()
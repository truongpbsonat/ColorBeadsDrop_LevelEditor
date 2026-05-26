# BallDropParty Python GUI Level Editor

Tool này dùng để tạo/sửa level JSON cho core gameplay BallDropParty.

## Chạy tool

```bash
python ball_drop_level_editor.py
```

Tool chỉ dùng thư viện chuẩn `tkinter`, không cần cài package ngoài.

## Cách dùng nhanh

1. Mở tool.
2. Tab **Grid**: chỉnh `Game Mode`, `Difficulty`, `Level`, `Category`, `Time`, `Level Name`, resize grid nếu cần.
3. Bên trái chọn brush:
   - `Shooter`: chọn màu + capacity, double-click vào ô grid để paint.
   - `Wall`: double-click vào ô để đặt wall.
   - `Tunnel`: nhập queue dạng `Blue:5, Red:6`, chọn output direction, double-click vào ô.
   - `Empty`: double-click để xóa.
4. Tab **Gate / Tray**: chỉnh gate/tray/layer bằng UI. Có thể dùng phần **Text Import / Export** để nhập nhanh theo cú pháp:
   ```text
   Gate 0:
   t_001: Blue:3, Orange:3, Purple:3
   t_002: Red5, Blue5

   Gate 1:
   Green4, Yellow4
   ```
   Bấm **Parse Text** nếu dùng text import.
5. Bấm **Validate** để kiểm tra lỗi cơ bản.
6. **Save As** để export `.json` vào Unity folder:
   `Assets/_Project/Levels/Classic/{level}.json`

## Lưu ý

- JSON tạo ra bám đúng `LevelData`: metadata Sonat (`gameMode`, `difficulty`, `level`, `category`) và gameplay data (`time`, `levelName`, `grid`, `gateSystem`).
- JSON grid dùng format `GridCellData.entity` polymorphic theo `type`.
- Có hỗ trợ ban đầu: `Shooter`, `Wall`, `Tunnel`.
- Validator hiện tại bám theo `Assets/_Project/Scripts/Gameplay/Level/LevelValidator.cs`:
  - grid size/cell bounds
  - shooter capacity/color
  - tunnel queue/output direction
  - obstacle và shooter group reference cơ bản
  - gate count / gate index
  - tray layer requiredCount
  - tổng capacity theo màu không được thiếu so với tray requirement

Runtime tuning như conveyor speed, spawn interval, lose delay, camera, spline/spawn scene refs nằm trên MonoBehaviour/ScriptableObject trong Unity, không nằm trong level JSON.

Đây là bản tool level editor đầu tiên để bạn dùng ngay trong production pipeline JSON-first.

## Cấu trúc source

- `ball_drop_level_editor.py`: launcher, giữ nguyên command chạy cũ.
- `ball_drop_editor/app.py`: Tkinter UI và workflow editor.
- `ball_drop_editor/level_data.py`: tạo/sửa LevelData, grid entity helpers.
- `ball_drop_editor/gate_text.py`: parse/export text cho gate/tray.
- `ball_drop_editor/validator.py`: validation rules.
- `ball_drop_editor/constants.py`, `ball_drop_editor/utils.py`: constants và helper nhỏ dùng chung.

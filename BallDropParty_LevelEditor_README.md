# BallDropParty Level Editor Tool – README

Tài liệu này mô tả **LevelData JSON** và các yêu cầu sử dụng trong tool `ball_drop_level_editor.py`.

Tool dùng để tạo nhanh level JSON cho core gameplay BallDropParty theo hướng **JSON-first**. Level JSON chỉ chứa nội dung level như grid, shooter, wall, tunnel, gate và tray. Runtime tuning như conveyor speed, spawn interval, lose delay, camera, spline/spawn scene refs nằm trên MonoBehaviour/ScriptableObject trong Unity.

---

## 1. Mục đích của tool

Tool Python GUI này giúp level designer/dev:

- Tạo level mới.
- Resize grid.
- Paint cell thành `Shooter`, `Wall`, `Tunnel`, hoặc `Empty`.
- Cấu hình shooter color/capacity và modifier `Hidden`/`Ice`.
- Cấu hình tunnel output direction và shooter queue.
- Cấu hình gate count, số tray visible mỗi gate.
- Nhập tray queue/layer bằng text format nhanh.
- Validate level cơ bản trước khi đưa vào Unity.
- Export JSON vào folder Unity.

Đường dẫn export khuyến nghị:

```text
Assets/_Project/Levels/Classic/{level}.json
```

---

## 2. Yêu cầu môi trường

### 2.1 Python

Tool chạy bằng Python 3 và chỉ dùng thư viện chuẩn.

Yêu cầu:

```text
Python 3.9+
Tkinter
```

Trên Windows, nếu cài Python từ python.org thì Tkinter thường đã có sẵn.

### 2.2 Chạy tool

Mở terminal/cmd tại thư mục chứa tool:

```bash
python ball_drop_level_editor.py
```

Nếu máy có nhiều version Python:

```bash
py ball_drop_level_editor.py
```

### 2.3 Cấu trúc source

```text
ball_drop_level_editor.py      launcher, giữ nguyên command chạy cũ
ball_drop_editor/app.py        Tkinter UI và workflow editor
ball_drop_editor/level_data.py LevelData/grid entity helpers
ball_drop_editor/gate_text.py  Gate/tray text import-export
ball_drop_editor/validator.py  Validation rules
ball_drop_editor/constants.py  Constants dùng chung
ball_drop_editor/utils.py      Helper nhỏ dùng chung
```

---

## 3. Tổng quan LevelData

Một file level JSON có cấu trúc chính:

```json
{
  "gameMode": "Classic",
  "difficulty": "Normal",
  "level": 1,
  "category": 0,
  "time": 60,
  "levelName": "Level 1",
  "grid": {},
  "gateSystem": {}
}
```

Các phần tool đang hỗ trợ trực tiếp:

| Field | Tool hỗ trợ | Ý nghĩa |
|---|---:|---|
| `gameMode` | Có | Metadata Sonat từ base `LevelData`. |
| `difficulty` | Có | Metadata độ khó từ base `LevelData`. |
| `level` | Có | Số level từ base `LevelData`. |
| `category` | Có | Category level từ base `LevelData`. |
| `time` | Có | Thời gian gameplay của level. |
| `levelName` | Có | Tên level. |
| `grid` | Có | Kích thước grid và danh sách cell/entity. |
| `gateSystem` | Có | Số gate, tray visible, tray queue. |

---

## 4. Grid data

### 4.1 Cấu trúc `grid`

```json
"grid": {
  "rows": 4,
  "columns": 4,
  "cells": [],
  "obstacles": [],
  "shooterGroups": []
}
```

`cellSize` vÃ  `boardOrigin` khÃ´ng náº±m trong level JSON. Hai giÃ¡ trá»‹ nÃ y Ä‘Æ°á»£c setup trÃªn `GridManager` trong Unity scene.

Quy ước tọa độ:

```text
row = 0 là hàng trên cùng.
column = 0 là cột bên trái.
rows tính từ trên xuống dưới.
columns tính từ trái sang phải.
```

Tool luôn tạo đủ `rows * columns` cell trong `grid.cells`.

---

### 4.2 Cấu trúc `GridCellData`

Mỗi cell có dạng:

```json
{
  "row": 0,
  "column": 0,
  "entity": null
}
```

`entity = null` nghĩa là ô trống.

Nếu ô có nội dung, `entity` là một object polymorphic có field `type`:

```json
{
  "row": 0,
  "column": 0,
  "entity": {
    "type": "Shooter",
    "entityId": "entity_s_0001",
    "blocksPath": true,
    "shooter": {}
  }
}
```

Tool hiện hỗ trợ 3 loại entity chính:

```text
Shooter
Wall
Tunnel
```

Các phần data chưa có UI edit đầy đủ:

```text
GridObstacle overlay như IceBlock
ShooterGroup
ShooterModifier riêng cho từng shooter trong queue tunnel (tool hiện apply/remove theo cả queue của tunnel đang chọn)
```

---

## 5. Shooter entity

### 5.1 JSON output

Khi paint brush `Shooter`, tool tạo data dạng:

```json
{
  "type": "Shooter",
  "entityId": "entity_s_001",
  "blocksPath": true,
  "shooter": {
    "shooterId": "s_001",
    "colorId": "Blue",
    "capacity": 5,
    "modifiers": []
  }
}
```

### 5.2 Field

| Field | Bắt buộc | Ý nghĩa |
|---|---:|---|
| `type` | Có | Luôn là `Shooter`. |
| `entityId` | Có | ID entity trên grid cell. |
| `blocksPath` | Có | Shooter chặn pathfinding. Mặc định `true`. |
| `shooter.shooterId` | Có | ID shooter gameplay. |
| `shooter.colorId` | Có | Màu gameplay của shooter/ball. |
| `shooter.capacity` | Có | Số ball nhỏ spawn ra khi shooter bắn. |
| `shooter.modifiers` | Có | Danh sách modifier `Hidden`/`Ice`/`Special`/`Hammer`/`Arrow`, chỉnh từ brush hoặc shooter grid đang chọn. Xem mục 5.4. |

### 5.3 Màu hợp lệ trong tool

Tool hiện có danh sách màu:

```text
Red
Blue
Yellow
Green
Purple
Cyan
Orange
Pink
Wild
```

`Wild` là màu đặc biệt, runtime cần check qua `ColorConfigManager.IsSameGameplayColor`.

### 5.4 Shooter modifiers

`shooter.modifiers` là list các object có field `type` (luôn là **tên enum dạng string**, không phải số):

```json
{ "type": "Hidden" }
{ "type": "Ice", "hp": 2 }
{ "type": "Special" }
{ "type": "Hammer", "color": "Blue" }
{ "type": "Arrow", "direction": "Up" }
```

| Type | Field thêm | Ý nghĩa |
|---|---|---|
| `Hidden` | – | Ẩn shooter cho tới khi lộ ra. |
| `Ice` | `hp` | Đóng băng shooter, cần phá `hp` lần. |
| `Special` | – | Shooter đặc biệt (capacity hiệu dụng x2). |
| `Hammer` | `color` | Búa phá `GlassBarrier` **cùng màu**. Không phải mechanic riêng — khi có Hammer, level được tính là dùng mechanic `GlassBarrier`. Chỉnh trong panel **Modifiers → Hammer** + combobox **Hammer Color**. |
| `Arrow` | `direction` | Mở khoá theo hướng `Up/Down/Left/Right`. Mechanic `ArrowShooter`. Chỉnh trong panel **Modifiers → Arrow** + combobox **Arrow Dir**. |

---

## 5b. GlassBarrier obstacle & ConnectedTray modifier

### GlassBarrier (grid obstacle)

Obstacle dạng đường thẳng giống `LockBar`, thêm `color`. Đặt trong tab **Grid Obstacles → type GlassBarrier**: chọn hướng + length (dùng chung control với LockBar) và **Color**.

```json
{
  "obstacleId": "glass_ab12",
  "type": "GlassBarrier",
  "direction": "Right",
  "length": 3,
  "color": "Blue",
  "shape": { "type": "LineHorizontal", "origin": { "row": 1, "column": 1 }, "width": 3, "height": 1, "cells": [] }
}
```

Chỉ một shooter có modifier `Hammer` cùng màu mới phá được barrier. Mechanic: `GlassBarrier`.

### ConnectedTray (tray modifier `RemoteConnected`)

Nối 2 tray ở 2 gate bằng cùng `connectionId`; cả hai mở khoá khi cùng ra front. Chỉnh trong **Gate Direct Edit → Tray Connect** + ô **Connection Id**.

```json
{ "type": "RemoteConnected", "connectionId": "link_a" }
```

Validator yêu cầu mỗi `connectionId` xuất hiện **đúng trên 2 tray** (lệch hoặc rỗng → error). Mechanic: `ConnectedTray`.

---

## 6. Wall entity

### 6.1 JSON output

Khi paint brush `Wall`, tool tạo:

```json
{
  "type": "Wall",
  "entityId": "wall_001",
  "blocksPath": true
}
```

### 6.2 Ý nghĩa

Wall là main entity chiếm cell và chặn pathfinding. Shooter không thể đi xuyên qua wall để tìm đường ra top row.

---

## 7. Tunnel entity

### 7.1 JSON output

Khi paint brush `Tunnel`, tool tạo:

```json
{
  "type": "Tunnel",
  "entityId": "tunnel_001",
  "blocksPath": true,
  "outputDirection": "Up",
  "shooterQueue": [
    {
      "shooterId": "s_tunnel_001",
      "colorId": "Blue",
      "capacity": 5,
      "modifiers": []
    },
    {
      "shooterId": "s_tunnel_002",
      "colorId": "Red",
      "capacity": 6,
      "modifiers": []
    }
  ]
}
```

### 7.2 Field

| Field | Bắt buộc | Ý nghĩa |
|---|---:|---|
| `type` | Có | Luôn là `Tunnel`. |
| `entityId` | Có | ID tunnel entity. |
| `blocksPath` | Có | Tunnel có chặn path hay không. Mặc định `true`. |
| `outputDirection` | Có | Hướng spawn shooter ra ngoài tunnel. |
| `shooterQueue` | Có | Queue shooter nằm trong tunnel. |

### 7.3 Direction hợp lệ

```text
Up
Down
Left
Right
```

### 7.4 Format nhập tunnel queue trong tool

Trong panel brush Tunnel, nhập queue dạng:

```text
Blue:5, Red:6, Orange:4
```

Hoặc:

```text
Blue5, Red6, Orange4
```

Mỗi item sẽ được convert thành một `ShooterData` trong `shooterQueue`.

---


## 8. GateSystem data

### 8.1 Cấu trúc

```json
"gateSystem": {
  "gateCount": 4,
  "maxVisibleTrayPerGate": 4,
  "gates": []
}
```

### 8.2 Field

| Field | Ý nghĩa |
|---|---|
| `gateCount` | Số gate/lane trong level. |
| `maxVisibleTrayPerGate` | Số tray hiển thị tối đa trên mỗi gate. |
| `gates` | Danh sách gate data. |

Yêu cầu:

```text
gateCount > 0
maxVisibleTrayPerGate > 0
gates.Count == gateCount
Mỗi gateIndex nằm trong [0, gateCount - 1]
Không duplicate gateIndex
```

---

## 9. GateData và TrayData

### 9.1 GateData

```json
{
  "gateIndex": 0,
  "trayQueue": []
}
```

`trayQueue` là toàn bộ hàng đợi tray của gate. Runtime chỉ hiển thị tối đa `maxVisibleTrayPerGate` tray cùng lúc.

### 9.2 TrayData

```json
{
  "trayId": "t_001",
  "layers": [
    { "colorId": "Blue", "requiredCount": 3 },
    { "colorId": "Orange", "requiredCount": 3 }
  ]
}
```

### 9.3 TrayLayerData

```json
{
  "colorId": "Blue",
  "requiredCount": 3
}
```

Field:

| Field | Ý nghĩa |
|---|---|
| `colorId` | Màu layer hiện tại cần nhận. |
| `requiredCount` | Số ball cần để complete layer. |

Rule gameplay:

```text
Tray chỉ nhận ball cho current layer.
Layer đầy thì chuyển sang layer tiếp theo.
Tray complete khi hết layer.
Gate complete khi trayQueue hết và activeTrays rỗng.
```

---

## 10. Format nhập Gate/Tray trong tool

Tool cho nhập tray queue bằng text để tạo nhanh `gateSystem.gates`.

### 10.1 Format có trayId rõ ràng

```text
Gate 0:
t_001: Blue:3, Orange:3, Purple:3
t_002: Red:5, Blue:5

Gate 1:
t_003: Green:4, Yellow:4
```

Kết quả:

```json
{
  "gateIndex": 0,
  "trayQueue": [
    {
      "trayId": "t_001",
      "layers": [
        { "colorId": "Blue", "requiredCount": 3 },
        { "colorId": "Orange", "requiredCount": 3 },
        { "colorId": "Purple", "requiredCount": 3 }
      ]
    },
    {
      "trayId": "t_002",
      "layers": [
        { "colorId": "Red", "requiredCount": 5 },
        { "colorId": "Blue", "requiredCount": 5 }
      ]
    }
  ]
}
```

### 10.2 Format không có trayId

```text
Gate 0:
Blue:3, Orange:3
Red5, Blue5
```

Tool sẽ tự sinh `trayId`.

### 10.3 Format layer hợp lệ

Các cách viết hợp lệ:

```text
Blue:3
Blue3
Orange:10
Purple10
```

Không nên dùng màu không có trong danh sách tool.

---

## 11. Validator trong tool

Tool có tab Validate để kiểm tra lỗi cơ bản.

### 11.1 Error đang check

- `grid.rows` hoặc `grid.columns` <= 0.
- Cell nằm ngoài phạm vi grid.
- Entity không có `type`.
- Entity type không thuộc danh sách tool hỗ trợ.
- Shooter thiếu `shooter` data.
- Shooter `capacity <= 0`.
- Shooter `colorId` không hợp lệ.
- Duplicate `shooterId`.
- Tunnel thiếu hoặc sai `outputDirection`.
- Tunnel queue có shooter capacity <= 0.
- `gateSystem.gateCount <= 0`.
- `maxVisibleTrayPerGate <= 0`.
- `gates.Count != gateCount`.
- Duplicate `gateIndex`.
- `gateIndex` ngoài range.
- Tray không có layer.
- Tray layer `requiredCount <= 0`.
- Tray layer `colorId` không hợp lệ.
- Tổng shooter capacity theo màu nhỏ hơn tổng tray required theo màu.

### 11.2 Warning đang check

- Gate không có `trayQueue`.
- Không có shooter nào trong grid/tunnel.
- Không có shooter active ban đầu chưa được tool simulate đầy đủ.

### 11.3 Giới hạn của validator bản đầu

Validator trong Python tool hiện là validator nhanh, chưa thay thế validator runtime/editor trong Unity.

Chưa simulate đầy đủ:

- Pathfinding active shooter theo wall/shooter/tunnel.
- Thứ tự click shooter có thể thắng hay không.
- Tunnel output bị chặn vĩnh viễn.
- Modifier của shooter trong queue tunnel được apply/remove theo toàn bộ queue của tunnel đang chọn, chưa chọn riêng từng queue item.
- Obstacle overlay như IceBlock.
- Connected shooter group.
- Wild color matching nâng cao.

---

## 12. Quy trình tạo level đề xuất

1. Mở tool.
2. Chọn `New` hoặc `Open JSON`.
3. Nhập `Game Mode`, `Difficulty`, `Level`, `Category`, `Time`, `Level Name`.
4. Set `Rows`, `Columns`, sau đó bấm resize/apply nếu cần.
5. Vào tab Grid.
6. Chọn brush:
   - `Shooter`: chọn màu + capacity.
   - `Wall`: đặt blocker.
   - `Tunnel`: nhập direction + queue.
   - `Empty`: xóa cell.
7. Double-click hoặc chọn cell rồi apply brush.
8. Vào tab Gate / Tray.
9. Set `Gate Count`, `Max Visible Tray / Gate`.
10. Nhập tray queue theo text format.
11. Bấm `Parse text to GateSystem`.
12. Bấm `Validate`.
13. Sửa lỗi nếu có.
14. Save JSON vào Unity.
15. Chạy Unity LevelValidator/runtime loader để kiểm tra lần cuối.

---

## 13. Ví dụ level JSON tối giản

```json
{
  "gameMode": "Classic",
  "difficulty": "Normal",
  "level": 1,
  "category": 0,
  "time": 60,
  "levelName": "Level 1",
  "grid": {
    "rows": 2,
    "columns": 2,
    "cells": [
      {
        "row": 0,
        "column": 0,
        "entity": {
          "type": "Shooter",
          "entityId": "entity_s_001",
          "blocksPath": true,
          "shooter": {
            "shooterId": "s_001",
            "colorId": "Blue",
            "capacity": 3,
            "modifiers": []
          }
        }
      },
      { "row": 0, "column": 1, "entity": null },
      { "row": 1, "column": 0, "entity": null },
      { "row": 1, "column": 1, "entity": null }
    ],
    "obstacles": [],
    "shooterGroups": []
  },
  "gateSystem": {
    "gateCount": 1,
    "maxVisibleTrayPerGate": 4,
    "gates": [
      {
        "gateIndex": 0,
        "trayQueue": [
          {
            "trayId": "t_001",
            "layers": [
              { "colorId": "Blue", "requiredCount": 3 }
            ]
          }
        ]
      }
    ]
  }
}
```

---

## 14. Các yêu cầu khi import vào Unity

Runtime Unity cần có:

- JSON loader dùng Newtonsoft.Json nếu dùng polymorphic converter.
- `GridEntityJsonConverter` cho `entity.type`.
- `ShooterModifierJsonConverter` nếu sau này bật modifier.
- `ColorConfigManager` để resolve/check màu.
- Runtime scene references và tuning được cấu hình trên MonoBehaviour/ScriptableObject.
- `LevelValidator` bên Unity để validate sâu hơn trước khi build runtime.

Không nên để runtime phụ thuộc trực tiếp vào dữ liệu UI của tool. Tool chỉ xuất JSON data.

---

## 15. Những thứ tool chưa nên làm ở bản đầu

Để giữ tool đơn giản và đúng phạm vi core, bản đầu chưa thêm:

- Win/Lose popup config.
- Coin/economy/reward.
- Ads/monetization.
- Save progression.
- Audio/music/SFX config.
- UI flow ngoài gameplay core.

Các phần này nên nằm ở module khác sau khi core gameplay ổn định.

---

## 16. Checklist trước khi commit level

Trước khi đưa JSON vào project:

- [ ] `level` đúng.
- [ ] `levelName` rõ ràng.
- [ ] Grid đúng kích thước.
- [ ] Không có cell ngoài bounds.
- [ ] Shooter có màu hợp lệ.
- [ ] Shooter capacity > 0.
- [ ] Tunnel queue đúng format.
- [ ] Gate count đúng số lane mong muốn.
- [ ] Mỗi gate có trayQueue hợp lý.
- [ ] Tray layer requiredCount > 0.
- [ ] Tổng capacity theo màu >= tổng requiredCount của tray theo màu.
- [ ] Bấm Validate trong tool không còn error.
- [ ] Chạy validator trong Unity không còn error.

---

## 17. Gợi ý mở rộng tool sau này

Các tính năng nên thêm ở bản tiếp theo:

- Visual pathfinding preview cho shooter active/inactive.
- Edit obstacle overlay: IceBlock, Chain, Fog.
- Inspector riêng cho từng shooter trong queue tunnel thay vì thao tác theo toàn bộ queue.
- Edit shooter group: Connected, Chain, Pair.
- Simulate đơn giản tổng màu và thứ tự mở grid.
- Preview gate/tray bằng UI trực quan thay vì text.
- Export nhiều level liên tiếp.
- Batch validate folder levels.
- Import/export color config.

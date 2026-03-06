# Deterministic Flip Tracker

这个仓库提供了一个“翻面后仍保持同一 ID”的确定性追踪器实现，并附带一个简单的**可视化界面**用于演示。

## 1. 环境准备

推荐 Python 3.10+。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip pytest
```

> 可视化界面不依赖第三方 Web 框架，使用 Python 标准库 `http.server`。

## 2. 运行测试

```bash
pytest -q
```

## 3. 启动可视化界面

```bash
python tracker_visual_ui.py --port 8000
```

然后在浏览器打开：

- `http://127.0.0.1:8000`

界面功能：

- **播放 / 暂停 / 重置** 演示帧。
- 按 `Track ID` 显示颜色。
- 用边框颜色展示面状态：
  - 绿色：`FRONT`
  - 橙色：`FLIP`
  - 灰色：`BACK`

## 4. 代码使用示例

```python
from deterministic_flip_tracker import Detection, DeterministicFlipTracker

tracker = DeterministicFlipTracker(
    max_speed=20.0,
    lane_centers_y=[120, 240],
    lane_tolerance=10,
    max_missed=8,
)

tracks = tracker.step([
    Detection(100, 120, face_prob=0.9),
    Detection(180, 120, face_prob=0.1),
])

for t in tracks:
    print(t.track_id, t.x, t.y, t.face_state)
```

## 5. 文件说明

- `deterministic_flip_tracker.py`：追踪器核心逻辑（速度门控、车道门控、no-crossing、翻面状态机）。
- `tracker_visual_ui.py`：可视化 UI 与演示数据接口。
- `test_deterministic_flip_tracker.py`：核心追踪行为测试。
- `test_tracker_visual_ui.py`：可视化演示数据测试。

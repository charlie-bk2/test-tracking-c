# 多个同形物体翻面后连续追踪实现方案

## 1. 问题定义与目标
在产线、棋盘、实验台等场景中，存在多个外观几乎一致的物体（棋子/芯片/零件）。
- 正面：可见编号、字符、图案。
- 背面：几乎无区分特征。
- 任务：即使翻面后标记不可见，仍持续跟踪每个个体 ID 的轨迹和当前坐标。

目标指标建议：
1. **ID 保持率（IDF1）** ≥ 95%。
2. **翻面后丢失恢复时延** < 300 ms。
3. **多目标实时性**：1080p 下 20~30 FPS（视硬件）。

---

## 2. 总体技术路线
建议采用“**检测 + 跟踪 + 状态机 + 物理约束 + 短时重识别**”混合架构：

1. **检测层**：每帧识别所有目标框（或分割轮廓）。
2. **运动跟踪层**：用卡尔曼滤波预测轨迹，并结合匈牙利算法做数据关联。
3. **翻面状态机**：识别“正面可见/翻转中/背面不可见”状态，改变关联权重。
4. **约束层**：引入速度上限、碰撞排斥、轨道/工位几何约束，减少 ID 交换。
5. **重识别层（可选）**：在背面条件下提取弱特征（边缘微缺陷、厚度阴影、红外差异），用于长遮挡恢复。

---

## 3. 系统分层设计

## 3.1 感知输入层
- 相机：建议全局快门，避免运动畸变。
- 光照：环形漫射光 + 偏振片，降低高光导致的漏检。
- 标定：完成内参标定和像素到平面坐标的映射（单应或手眼标定）。

输出：
- 时间戳 `t`
- 目标检测集合 `D_t = {d_i}`，每个 `d_i` 含 `bbox, center, confidence, face_prob`

## 3.2 跟踪核心层
为每个 ID 建立 Track：
- 状态向量：`x = [cx, cy, vx, vy, w, h]`
- 协方差：`P`
- 生命周期：`Tentative/Confirmed/Lost/Removed`
- 面状态：`Front/Flip/Back`

核心算法：
- 预测：Kalman `x(t|t-1)`
- 关联：匈牙利算法最小化代价矩阵
  - 位置代价：马氏距离
  - 形状代价：`|w-h|` 相似度
  - 面状态一致性代价
- 更新：匹配成功后更新滤波器；未匹配进入 `Lost`

## 3.3 状态机层（关键）
每个 Track 都维护翻面状态机：
- `Front`: 可见正面标记（置信度高）
- `Flip`: 检测到角速度变化、短时遮挡或外形急变
- `Back`: 正面标记持续不可见，但轨迹连续

状态转移示例：
- `Front -> Flip`：连续 `k1` 帧正面置信度下降 + 姿态变化
- `Flip -> Back`：连续 `k2` 帧无正面标记且轨迹连续
- `Back -> Front`：再次检测到正面标记并通过几何门限校验

> 重点：在 `Back` 状态中，禁止仅靠“外观相似度”关联，改用运动与约束为主。

## 3.4 约束与冲突消解层
针对“长得一样”问题，必须引入场景约束：

1. **最大速度约束**：
   `||p_t - p_{t-1}|| <= v_max * dt`，超出则拒绝关联。

2. **不可穿越约束**（工装、轨道、棋盘格）：
   若预测轨迹跨越障碍区域，关联代价加大或剔除。

3. **邻近冲突处理**：
   当两个 Track 进入近距离交会区：
   - 提升帧率/快门
   - 临时缩小门限，保守保持原 ID
   - 交会结束后按轨迹平滑度选最优分配

## 3.5 重识别与恢复层（可选增强）
背面完全一致时，普通 ReID 效果有限，但仍可尝试：
- 微纹理特征（高分辨率）
- 边缘缺口/划痕（工业件常见）
- 多光谱（IR/UV）差异
- 重量/磁响应（若可加传感器）

恢复策略：
- `Lost` 在 `T_lost` 窗口内保留轨迹记忆。
- 新检测进入时先做几何门控，再做弱 ReID 复核。
- 超时仍未匹配则 `Removed`，同时输出不确定告警。

---

## 4. 推荐实现流程（工程落地）

1. **数据采集与标注**
   - 场景覆盖：翻面、遮挡、交叉、堆叠、快速移动。
   - 标注内容：检测框 + Track ID + 面状态（Front/Back）。

2. **训练检测器**
   - 模型：YOLOv8/RT-DETR 等实时模型。
   - 输出新增头：`face_prob`（正面可见概率）。

3. **集成多目标跟踪**
   - 基线：ByteTrack/BoT-SORT。
   - 增加：状态机与约束代价项。

4. **在线参数自适应**
   - 根据局部拥挤度动态调整关联门限。
   - 根据速度统计调整 `Q/R`（卡尔曼噪声）。

5. **评估与回归测试**
   - 指标：MOTA、IDF1、ID Switch、HOTA。
   - 重点测试集：高相似 + 翻面 + 交叉。

---

## 5. 伪代码（简化）

```python
for frame in stream:
    detections = detector(frame)  # bbox, conf, face_prob

    # 1) track prediction
    for trk in tracks:
        trk.predict()

    # 2) build cost matrix (motion + shape + state consistency + constraints)
    C = build_cost(tracks, detections, constraints=True)

    # 3) assignment
    matches, unmatch_trk, unmatch_det = hungarian_with_gating(C)

    # 4) update matched tracks
    for t_idx, d_idx in matches:
        tracks[t_idx].update(detections[d_idx])
        tracks[t_idx].update_face_state(detections[d_idx].face_prob)

    # 5) unmatched tracks
    for t_idx in unmatch_trk:
        tracks[t_idx].mark_lost()

    # 6) new tracks from unmatched detections
    for d_idx in unmatch_det:
        spawn_track(detections[d_idx])

    # 7) lost track recovery / remove timeout
    recover_or_remove(tracks)

    output(tracks)
```

---

## 6. 关键参数建议
- `max_age`（失配保留帧数）：15~40（按 FPS 调整）
- `iou_gate`：0.1~0.3（高相似场景建议更严）
- `mahalanobis_gate`：9~16
- `front_to_back_k`：3~8 帧
- `back_to_front_k`：2~5 帧

调参原则：
- 先保证低 ID Switch，再追求召回。
- 拥挤场景优先依赖运动模型与约束，不要依赖外观相似度。

---

## 7. 风险与对策
1. **大规模遮挡导致轨迹中断**
   - 对策：增加相机视角（双目/顶视+侧视）并做跨视角融合。

2. **高速翻转导致检测抖动**
   - 对策：短曝光、增光照、提升快门与 FPS。

3. **完全同质且无任何可区分特征**
   - 对策：在流程上增加“最小可观测差异”（微点标、不可见光油墨、工位时序约束）。

---

## 8. 最小可用版本（MVP）建议
若需要先快速上线，可按以下顺序实现：
1. 检测（bbox）
2. Kalman + 匈牙利关联
3. Front/Back 状态机
4. 最大速度约束
5. ID Switch 监控面板

该 MVP 往往已经可覆盖多数“翻面后继续追踪”需求，后续再按误差案例补充 ReID 与多传感器融合。

---

## 9. “100%追踪成功”落地策略（工程可执行版）

> 结论先行：在开放场景里无法数学保证 100%，但在**受控工位**可通过“流程约束 + 算法硬门控”做到工程上 100%（回归集 0 次 ID Switch）。

### 9.1 约束前提（必须满足）
1. 物体运行在固定通道（lane）内，不允许跨通道。
2. 速度有明确上限 `v_max`，相机 FPS 与快门足以覆盖位移。
3. 工艺上禁止超车/穿插（No-Crossing）。
4. 遮挡时长不超过 `max_missed` 对应时间窗。

只要违反以上任一前提，就应降级为“高成功率”而非“100%保证”。

### 9.2 策略优化点（相较通用 MOT）
1. **关联优先级重排**：运动与几何约束 > 外观相似度。
2. **强门控**：超速、越 lane、顺序反转直接拒绝匹配。
3. **翻面状态机**：进入 Back 后，禁用外观主导匹配。
4. **冲突处理保守化**：宁可新建轨迹 + 告警，也不允许错绑 ID。

### 9.3 已编码实现
仓库新增 `deterministic_flip_tracker.py`，实现了：
- 目标结构：`Detection`、`Track`、`FaceState`
- 核心跟踪器：`DeterministicFlipTracker`
- 关键机制：
  - 最大速度门控
  - Lane 门控
  - No-Crossing（顺序不反转）约束
  - Front/Flip/Back 状态机

并新增 `test_deterministic_flip_tracker.py` 验证：
- 翻面后持续追踪保持 ID 不变
- 交叉反转时拒绝错误匹配

### 9.4 使用示例
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
```

> 建议：上线时把“被硬门控拒绝的检测”接入告警看板，用于反向定位工艺异常（超速、串道、交叉）。

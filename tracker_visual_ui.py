"""Simple browser-based visualization for DeterministicFlipTracker.

Run:
    python tracker_visual_ui.py --port 8000
Then open http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List

from deterministic_flip_tracker import Detection, DeterministicFlipTracker


HTML_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Deterministic Flip Tracker 可视化</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }
    h1 { margin-bottom: 8px; }
    .row { display: flex; gap: 16px; align-items: center; margin-bottom: 12px; }
    #canvas { border: 1px solid #d1d5db; background: #f9fafb; }
    .legend span { margin-right: 10px; }
    button { padding: 6px 12px; cursor: pointer; }
    #status { font-size: 14px; color: #374151; }
  </style>
</head>
<body>
  <h1>DeterministicFlipTracker 可视化界面</h1>
  <div class="row">
    <button id="play">播放</button>
    <button id="pause">暂停</button>
    <button id="reset">重置</button>
    <span id="status">加载中...</span>
  </div>
  <canvas id="canvas" width="900" height="320"></canvas>
  <p class="legend">
    <span>轨迹颜色：按 Track ID 自动分配</span>
    <span>点边框：<b>FRONT</b>=绿色，<b>FLIP</b>=橙色，<b>BACK</b>=灰色</span>
  </p>

  <script>
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    const statusEl = document.getElementById('status');
    let frames = [];
    let i = 0;
    let timer = null;

    function colorForId(id) {
      const palette = ['#2563eb', '#dc2626', '#7c3aed', '#059669', '#d97706', '#0ea5e9'];
      return palette[(id - 1) % palette.length];
    }

    function faceStroke(face) {
      if (face === 'front') return '#16a34a';
      if (face === 'flip') return '#f59e0b';
      return '#6b7280';
    }

    function drawLanes() {
      ctx.save();
      ctx.strokeStyle = '#d1d5db';
      ctx.setLineDash([6, 6]);
      [100, 220].forEach(y => {
        ctx.beginPath();
        ctx.moveTo(20, y);
        ctx.lineTo(880, y);
        ctx.stroke();
      });
      ctx.restore();
    }

    function drawFrame(frame) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      drawLanes();

      frame.tracks.forEach(t => {
        const color = colorForId(t.track_id);
        ctx.fillStyle = color;
        ctx.strokeStyle = faceStroke(t.face_state);
        ctx.lineWidth = 3;

        ctx.beginPath();
        ctx.arc(t.x, t.y, 10, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#111827';
        ctx.font = '12px Arial';
        ctx.fillText(`ID ${t.track_id} (${t.face_state})`, t.x + 12, t.y - 12);
      });

      statusEl.innerText = `帧 ${frame.frame_index + 1} / ${frames.length}`;
    }

    async function loadData() {
      const resp = await fetch('/api/simulate');
      const data = await resp.json();
      frames = data.frames;
      i = 0;
      drawFrame(frames[i]);
    }

    function play() {
      if (timer || !frames.length) return;
      timer = setInterval(() => {
        i = (i + 1) % frames.length;
        drawFrame(frames[i]);
      }, 450);
    }

    function pause() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    }

    function reset() {
      pause();
      i = 0;
      if (frames.length) drawFrame(frames[i]);
    }

    document.getElementById('play').addEventListener('click', play);
    document.getElementById('pause').addEventListener('click', pause);
    document.getElementById('reset').addEventListener('click', reset);

    loadData().catch(err => {
      statusEl.innerText = '加载失败: ' + err.message;
    });
  </script>
</body>
</html>
"""


def build_demo_sequence() -> List[List[Detection]]:
    """Frames with two objects moving in the same lane and flipping face state."""
    return [
        [Detection(80, 100, face_prob=0.95), Detection(160, 220, face_prob=0.95)],
        [Detection(100, 100, face_prob=0.90), Detection(180, 220, face_prob=0.90)],
        [Detection(120, 100, face_prob=0.50), Detection(200, 220, face_prob=0.50)],
        [Detection(140, 100, face_prob=0.12), Detection(220, 220, face_prob=0.10)],
        [Detection(160, 100, face_prob=0.08), Detection(240, 220, face_prob=0.08)],
        [Detection(180, 100, face_prob=0.06), Detection(260, 220, face_prob=0.06)],
    ]


def simulate_frames() -> List[Dict[str, object]]:
    tracker = DeterministicFlipTracker(
        max_speed=35.0,
        lane_centers_y=[100, 220],
        lane_tolerance=14,
        max_missed=4,
    )
    output = []
    for idx, frame_dets in enumerate(build_demo_sequence()):
        tracks = tracker.step(frame_dets)
        output.append(
            {
                "frame_index": idx,
                "tracks": [
                    {
                        "track_id": t.track_id,
                        "x": t.x,
                        "y": t.y,
                        "face_state": t.face_state.value,
                        "missed": t.missed,
                    }
                    for t in tracks
                ],
            }
        )
    return output


class TrackerHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            body = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/simulate":
            payload = json.dumps({"frames": simulate_frames()}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_response(404)
        self.end_headers()


def run_server(port: int) -> None:
    server = HTTPServer(("0.0.0.0", port), TrackerHandler)
    print(f"Tracker UI running on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run tracker visualization UI")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run_server(args.port)

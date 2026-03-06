"""Deterministic tracker for near-identical objects that may flip front/back."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


class FaceState(str, Enum):
    FRONT = "front"
    FLIP = "flip"
    BACK = "back"


@dataclass(frozen=True)
class Detection:
    x: float
    y: float
    face_prob: float = 0.0
    confidence: float = 1.0


@dataclass
class Track:
    track_id: int
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    face_state: FaceState = FaceState.BACK
    missed: int = 0
    hits: int = 1
    front_streak: int = 0
    back_streak: int = 0
    history: List[Tuple[float, float]] = field(default_factory=list)

    def predict(self, dt: float = 1.0) -> Tuple[float, float]:
        return self.x + self.vx * dt, self.y + self.vy * dt

    def update(self, det: Detection, dt: float = 1.0) -> None:
        new_vx = (det.x - self.x) / dt
        new_vy = (det.y - self.y) / dt
        self.vx = 0.7 * self.vx + 0.3 * new_vx
        self.vy = 0.7 * self.vy + 0.3 * new_vy
        self.x = det.x
        self.y = det.y
        self.history.append((self.x, self.y))
        self.hits += 1
        self.missed = 0
        self._update_face_state(det.face_prob)

    def mark_missed(self) -> None:
        self.missed += 1

    def _update_face_state(self, face_prob: float) -> None:
        if face_prob >= 0.8:
            self.front_streak += 1
            self.back_streak = 0
        elif face_prob <= 0.2:
            self.back_streak += 1
            self.front_streak = 0
        else:
            self.front_streak = 0
            self.back_streak = 0
            self.face_state = FaceState.FLIP
            return

        if self.front_streak >= 2:
            self.face_state = FaceState.FRONT
        elif self.back_streak >= 2:
            self.face_state = FaceState.BACK


class DeterministicFlipTracker:
    """Constraint-first deterministic tracker.

    100% tracking is only realistic under a controlled envelope:
    - bounded speed
    - known lane geometry
    - no crossing / no overtaking
    """

    def __init__(
        self,
        max_speed: float,
        lane_centers_y: Optional[Sequence[float]] = None,
        lane_tolerance: float = 12.0,
        max_missed: int = 10,
    ) -> None:
        self.max_speed = max_speed
        self.lane_centers_y = list(lane_centers_y or [])
        self.lane_tolerance = lane_tolerance
        self.max_missed = max_missed
        self.tracks: Dict[int, Track] = {}
        self._next_id = 1

    def step(self, detections: Iterable[Detection], dt: float = 1.0) -> List[Track]:
        dets = [d for d in detections if d.confidence >= 0.2]
        candidates = self._build_candidates(dets, dt)
        assignments = self._greedy_assign(candidates, dets)

        assigned_tracks = set()
        assigned_dets = set()
        for track_id, det_idx in assignments:
            track = self.tracks[track_id]
            track.update(dets[det_idx], dt=dt)
            assigned_tracks.add(track_id)
            assigned_dets.add(det_idx)

        for track_id, track in list(self.tracks.items()):
            if track_id not in assigned_tracks:
                track.mark_missed()
                if track.missed > self.max_missed:
                    del self.tracks[track_id]

        for det_idx, det in enumerate(dets):
            if det_idx not in assigned_dets:
                self._spawn_track(det)

        return self.active_tracks()

    def active_tracks(self) -> List[Track]:
        return sorted(self.tracks.values(), key=lambda t: t.track_id)

    def _spawn_track(self, det: Detection) -> None:
        tr = Track(track_id=self._next_id, x=det.x, y=det.y)
        tr.history.append((det.x, det.y))
        tr._update_face_state(det.face_prob)
        self.tracks[self._next_id] = tr
        self._next_id += 1

    def _build_candidates(self, dets: List[Detection], dt: float) -> List[Tuple[float, int, int]]:
        candidates: List[Tuple[float, int, int]] = []
        for tid, tr in self.tracks.items():
            px, py = tr.predict(dt)
            for i, det in enumerate(dets):
                if not self._lane_ok(det):
                    continue
                dx = det.x - px
                dy = det.y - py
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > self.max_speed * dt:
                    continue
                face_penalty = 0.0
                if tr.face_state == FaceState.FRONT and det.face_prob < 0.2:
                    face_penalty = 1.5
                cost = dist + face_penalty
                candidates.append((cost, tid, i))
        return sorted(candidates, key=lambda x: x[0])

    def _greedy_assign(
        self, candidates: List[Tuple[float, int, int]], dets: Sequence[Detection]
    ) -> List[Tuple[int, int]]:
        used_tracks = set()
        used_dets = set()
        out: List[Tuple[int, int]] = []

        for _, tid, did in candidates:
            if tid in used_tracks or did in used_dets:
                continue
            if self._violates_no_crossing(tid, did, out, dets):
                continue
            used_tracks.add(tid)
            used_dets.add(did)
            out.append((tid, did))
        return out

    def _lane_ok(self, det: Detection) -> bool:
        if not self.lane_centers_y:
            return True
        best = min(abs(det.y - y) for y in self.lane_centers_y)
        return best <= self.lane_tolerance

    def _violates_no_crossing(
        self,
        track_id: int,
        det_id: int,
        assignments: Sequence[Tuple[int, int]],
        dets: Sequence[Detection],
    ) -> bool:
        """Prevent x-order inversion between assigned pairs."""
        current = self.tracks[track_id]
        new_x = dets[det_id].x
        for other_tid, other_did in assignments:
            other = self.tracks[other_tid]
            other_new_x = dets[other_did].x
            prev_order = current.x <= other.x
            next_order = new_x <= other_new_x
            if prev_order != next_order:
                return True
        return False

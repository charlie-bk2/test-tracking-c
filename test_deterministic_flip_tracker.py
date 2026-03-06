import unittest

from deterministic_flip_tracker import Detection, DeterministicFlipTracker, FaceState


class TestDeterministicFlipTracker(unittest.TestCase):
    def test_id_kept_after_flip_without_crossing(self):
        trk = DeterministicFlipTracker(max_speed=15.0, lane_centers_y=[10], lane_tolerance=5)

        trk.step([Detection(10, 10, face_prob=0.95), Detection(30, 10, face_prob=0.92)])
        ids = [t.track_id for t in trk.active_tracks()]
        self.assertEqual(ids, [1, 2])

        trk.step([Detection(14, 10, face_prob=0.1), Detection(34, 10, face_prob=0.1)])
        trk.step([Detection(18, 10, face_prob=0.05), Detection(38, 10, face_prob=0.05)])

        tracks = trk.active_tracks()
        self.assertEqual([t.track_id for t in tracks], [1, 2])
        self.assertEqual(tracks[0].face_state, FaceState.BACK)
        self.assertEqual(tracks[1].face_state, FaceState.BACK)

    def test_no_crossing_constraint_preserves_order(self):
        trk = DeterministicFlipTracker(max_speed=30.0)
        trk.step([Detection(10, 0), Detection(20, 0)])

        trk.step([Detection(22, 0), Detection(8, 0)])
        tracks = trk.active_tracks()

        t1 = [t for t in tracks if t.track_id == 1][0]
        t2 = [t for t in tracks if t.track_id == 2][0]

        # no-crossing keeps relative order in assignment result
        self.assertLessEqual(t1.x, t2.x)


if __name__ == "__main__":
    unittest.main()

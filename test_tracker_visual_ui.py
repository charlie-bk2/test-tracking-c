from tracker_visual_ui import simulate_frames


def test_simulate_frames_shape_and_ids_stable() -> None:
    frames = simulate_frames()
    assert len(frames) >= 2

    first_ids = [t["track_id"] for t in frames[0]["tracks"]]
    assert len(first_ids) == 2

    for frame in frames[1:]:
        ids = [t["track_id"] for t in frame["tracks"]]
        assert ids == first_ids


def test_simulate_frames_contains_back_state_after_flip() -> None:
    frames = simulate_frames()
    all_states = [t["face_state"] for frame in frames for t in frame["tracks"]]
    assert "back" in all_states

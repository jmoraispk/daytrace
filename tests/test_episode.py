from dataclasses import FrozenInstanceError

import pytest


def test_episode_factory_preserves_source_membership(make_episode) -> None:
    episode = make_episode(session_ids=("session-001", "session-002"))

    assert episode.episode_id == "episode-001"
    assert episode.session_ids == ("session-001", "session-002")
    with pytest.raises(FrozenInstanceError):
        episode.label = "changed"

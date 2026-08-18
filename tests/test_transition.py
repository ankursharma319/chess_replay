from pathlib import Path

from PIL import Image

from chess_replay.rendering.transition import TransitionPresentation, TransitionRenderer


def test_renders_tournament_result_transition(tmp_path: Path) -> None:
    output = tmp_path / "transition.png"
    TransitionRenderer(960, 540).render(
        TransitionPresentation(
            player_name="Magnus Carlsen",
            player_title="GM",
            opponent_name="Opponent",
            result_label="Won",
            score_after=3.5,
            wins=3,
            draws=1,
            losses=0,
            round_number=4,
            total_rounds=11,
            tournament_name="Titled Tuesday",
            next_opponent="Next Player",
        ),
        output,
    )

    with Image.open(output) as image:
        assert image.size == (960, 540)
        assert image.format == "PNG"
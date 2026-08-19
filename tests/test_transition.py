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
            opponent_title="IM",
            result_label="Won",
            termination_label="Checkmate",
            game_format="Blitz 3+1",
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

    presentation = TransitionPresentation(
        player_name="Magnus Carlsen",
        player_title="GM",
        opponent_name="Opponent",
        opponent_title="IM",
        result_label="Lost",
        termination_label="Time Out",
        game_format="Blitz 3+1",
        score_after=3.5,
        wins=3,
        draws=1,
        losses=1,
        round_number=5,
        total_rounds=11,
        tournament_name="Titled Tuesday",
    )
    assert presentation.outcome_heading == "MAGNUS CARLSEN LOST"
    assert presentation.matchup_line == "GM Magnus Carlsen vs IM Opponent"

    with Image.open(output) as image:
        assert image.size == (960, 540)
        assert image.format == "PNG"
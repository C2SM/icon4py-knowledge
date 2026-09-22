import run


def test_current_and_proposed_agree() -> None:
    assert run.compare(run.run_current(), run.run_proposed()) == []

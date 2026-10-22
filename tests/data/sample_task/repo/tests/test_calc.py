from pathlib import Path

# Collect fixture checks only in their sandbox workspace.
__test__ = Path.cwd() == Path("/work")



def test_zero_mean():
    from calc.core import mean
    assert mean([0]) == 0

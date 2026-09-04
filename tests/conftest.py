import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from tests.m0_support import ModelSpy, synthetic_msab_catalog_shape


@pytest.fixture
def model_spy():
    return ModelSpy()


@pytest.fixture
def msab_catalog_shape():
    return synthetic_msab_catalog_shape()

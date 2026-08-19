# -*- coding: utf-8 -*-
import pytest

from pysme.large_file_storage import setup_atmo, setup_nlte

from .conftest import datafiles_available


def lfs_available():
    return datafiles_available(setup_atmo(), "marcs2012.sav") and datafiles_available(
        setup_nlte(), "nlte_Ca_pysme.grd"
    )


skipif_lfs = pytest.mark.skipif(not lfs_available(), reason="LFS not available")


@pytest.fixture
def lfs_nlte():
    lfs_nlte = setup_nlte()
    yield lfs_nlte


@pytest.fixture
def lfs_atmo():
    lfs_atmo = setup_atmo()
    yield lfs_atmo

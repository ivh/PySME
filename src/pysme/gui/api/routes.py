# -*- coding: utf-8 -*-
"""API routes for PySME web GUI."""

import asyncio
import io
import json
import logging
import tempfile
import threading
import time as _time
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from ...sme import SME_Structure
from ...synthesize import synthesize_spectrum
from ...solve import SME_Solver
from .models import (
    AbundanceFitSettings,
    AbundPatternUpdate,
    BuiltinLinelistRequest,
    ContinuumSettings,
    FitResult,
    FitSettings,
    InstrumentSettings,
    LinelistInfo,
    MaskUpdate,
    MCMCRequest,
    MCMCResult,
    MultiSegmentWaveLimits,
    NLTESettings,
    RadialVelocitySettings,
    SessionState,
    SpectrumData,
    StellarParams,
    SolveRequest,
    SynthesizeRequest,
    WaveLimitsUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

LINELIST_DIR = Path(__file__).parent.parent / "data" / "linelists"


class _SessionLogHandler(logging.Handler):
    """Captures log messages into the session's log buffer."""

    def __init__(self, session_ref):
        super().__init__()
        self._session = session_ref

    def emit(self, record):
        try:
            self._session.log_entries.append({
                "type": "log",
                "time": _time.time(),
                "level": record.levelname,
                "message": self.format(record),
            })
        except Exception:
            pass


class Session:
    """In-memory session holding the current SME_Structure."""

    def __init__(self):
        self.sme: Optional[SME_Structure] = None
        self.filename: Optional[str] = None
        self.abund_pattern: str = "asplund2021"
        self.nlte_enabled: bool = False
        self.fit_abundances: list[str] = []
        self.solver: Optional[SME_Solver] = None
        self.solve_task: Optional[threading.Thread] = None
        self.solve_cancelled: bool = False
        self.solve_progress: list[dict] = []
        self.solve_done: bool = False
        self.solve_error: Optional[str] = None
        self.mcmc_runner = None
        self.mcmc_task: Optional[threading.Thread] = None
        self.mcmc_done: bool = False
        self.mcmc_error: Optional[str] = None
        self.mcmc_results: Optional[dict] = None
        self.log_entries: list[dict] = []
        self._setup_log_capture()

    def _setup_log_capture(self):
        handler = _SessionLogHandler(self)
        handler.setFormatter(logging.Formatter("%(name)s - %(message)s"))
        handler.setLevel(logging.DEBUG)
        pysme_logger = logging.getLogger("pysme")
        pysme_logger.addHandler(handler)
        pysme_logger.setLevel(logging.INFO)

    def reset(self):
        self.sme = None
        self.filename = None
        self.abund_pattern = "asplund2021"
        self.nlte_enabled = False
        self.fit_abundances = []
        self.log_entries.clear()
        self.cancel_solve()
        self.cancel_mcmc()

    def cancel_mcmc(self):
        self.mcmc_runner = None
        self.mcmc_task = None
        self.mcmc_done = False
        self.mcmc_error = None
        self.mcmc_results = None

    def cancel_solve(self):
        self.solve_cancelled = True
        self.solver = None
        self.solve_task = None
        self.solve_progress = []
        self.solve_done = False
        self.solve_error = None


session = Session()


@router.post("/session/new")
async def new_session():
    """Create a new empty SME_Structure."""
    session.reset()
    session.sme = SME_Structure()
    session.filename = None
    return {"status": "ok", "message": "New session created"}


@router.post("/session/load")
async def load_session(file: UploadFile = File(...)):
    """Load an SME file (.sme, .npy, .npz)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in [".sme", ".npy", ".npz", ".sav", ".inp", ".out", ".ech", ".fits"]:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        session.reset()
        session.sme = SME_Structure.load(tmp_path)
        session.filename = file.filename

        Path(tmp_path).unlink(missing_ok=True)

        return {
            "status": "ok",
            "message": f"Loaded {file.filename}",
            "nseg": session.sme.nseg if session.sme.wave is not None else 0,
        }
    except Exception as e:
        logger.exception("Failed to load file")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/session/load-test")
async def load_test_spectrum():
    """Load a test setup with solar-like parameters."""
    from ...abund import Abund

    session.reset()
    sme = SME_Structure()
    sme.teff = 5778
    sme.logg = 4.44
    sme.monh = 0.0
    sme.vmic = 1.0
    sme.vmac = 2.0
    sme.vsini = 2.0
    sme.abund = Abund(monh=0.0, pattern="asplund2021")
    sme.wran = np.array([[6436, 6444]])
    sme.ipres = 50000
    sme.iptype = "gauss"

    session.sme = sme
    session.filename = "test_spectrum"

    return {"status": "ok", "message": "Test spectrum loaded with solar parameters (6436-6444 A)"}


@router.post("/session/load-solar")
async def load_solar_spectrum():
    """Load the NSO solar atlas as observed spectrum."""
    from ...nso import load_solar_spectrum as _load_solar
    from ...abund import Abund
    from ...iliffe_vector import Iliffe_vector

    try:
        wave, flux = _load_solar()

        session.reset()
        sme = SME_Structure()
        sme.teff = 5778
        sme.logg = 4.44
        sme.monh = 0.0
        sme.vmic = 1.0
        sme.vmac = 2.0
        sme.vsini = 2.0
        sme.abund = Abund(monh=0.0, pattern="asplund2021")

        # Default window (matches bundled solar linelist)
        wl_min, wl_max = 6436.0, 6444.0
        mask = (wave >= wl_min) & (wave <= wl_max)
        w = wave[mask]
        f = flux[mask]

        sme.wave = Iliffe_vector([w])
        sme.spec = Iliffe_vector([f])
        sme.mask = Iliffe_vector([np.ones_like(f, dtype=int)])
        sme.wran = np.array([[wl_min, wl_max]])
        sme.ipres = 350000
        sme.iptype = "gauss"

        session.sme = sme
        session.filename = "nso_solar_atlas"

        return {
            "status": "ok",
            "message": f"NSO solar atlas loaded ({wl_min}-{wl_max} A, {len(w)} points)",
            "npoints": len(w),
            "wl_min": float(w.min()),
            "wl_max": float(w.max()),
        }
    except Exception as e:
        logger.exception("Failed to load solar spectrum")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session", response_model=SessionState)
async def get_session():
    """Get current session state."""
    if session.sme is None:
        return SessionState()

    sme = session.sme
    return SessionState(
        has_observation=sme.spec is not None and len(sme.spec) > 0,
        has_synthetic=sme.synth is not None and len(sme.synth) > 0 and len(sme.synth[0]) > 0,
        has_linelist=sme.linelist is not None and len(sme.linelist) > 0,
        nseg=sme.nseg if sme.wave is not None else 0,
        filename=session.filename,
        stellar_params=StellarParams(
            teff=float(sme.teff) if sme.teff is not None else None,
            logg=float(sme.logg) if sme.logg is not None else None,
            monh=float(sme.monh) if sme.monh is not None else None,
            vmic=float(sme.vmic) if sme.vmic is not None else None,
            vmac=float(sme.vmac) if sme.vmac is not None else None,
            vsini=float(sme.vsini) if sme.vsini is not None else None,
        ),
        fit_settings=FitSettings(
            fit_teff="teff" in (sme.fitparameters or []),
            fit_logg="logg" in (sme.fitparameters or []),
            fit_monh="monh" in (sme.fitparameters or []),
            fit_vmic="vmic" in (sme.fitparameters or []),
            fit_vmac="vmac" in (sme.fitparameters or []),
            fit_vsini="vsini" in (sme.fitparameters or []),
        ),
        instrument=InstrumentSettings(
            ipres=float(np.mean(sme.ipres)) if sme.ipres is not None and len(sme.ipres) > 0 else None,
            iptype=sme.iptype or "gauss",
            vrad=float(sme.vrad[0]) if sme.vrad is not None and len(sme.vrad) > 0 else None,
            snr=None,
        ),
        continuum=ContinuumSettings(
            cscale_flag=sme.cscale_flag or "linear",
            cscale_type=sme.cscale_type or "match",
        ),
        radial_velocity=RadialVelocitySettings(
            vrad_flag=sme.vrad_flag or "whole",
        ),
        abund_pattern=session.abund_pattern,
        wran=sme.wran.tolist() if sme.wran is not None else None,
        nlte_enabled=session.nlte_enabled,
        fit_abundances=session.fit_abundances,
        available_elements=_get_available_elements(sme),
    )


def _get_available_elements(sme: SME_Structure) -> list[str]:
    """Get unique elements from linelist."""
    if sme.linelist is None or len(sme.linelist) == 0:
        return []
    try:
        species = sme.linelist.species
        elements = set()
        for s in species:
            elem = s.split()[0].strip("0123456789")
            if elem:
                elements.add(elem)
        return sorted(elements)
    except Exception:
        return []


@router.post("/session/save")
async def save_session():
    """Save current SME_Structure to a downloadable file."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    try:
        with tempfile.NamedTemporaryFile(suffix=".sme", delete=False) as tmp:
            session.sme.save(tmp.name)
            tmp_path = tmp.name

        filename = session.filename or "spectrum.sme"
        if not filename.endswith(".sme"):
            filename = Path(filename).stem + ".sme"

        return FileResponse(
            tmp_path,
            media_type="application/octet-stream",
            filename=filename,
            background=None,
        )
    except Exception as e:
        logger.exception("Failed to save file")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/params", response_model=StellarParams)
async def get_params():
    """Get stellar parameters."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    sme = session.sme
    return StellarParams(
        teff=float(sme.teff) if sme.teff is not None else None,
        logg=float(sme.logg) if sme.logg is not None else None,
        monh=float(sme.monh) if sme.monh is not None else None,
        vmic=float(sme.vmic) if sme.vmic is not None else None,
        vmac=float(sme.vmac) if sme.vmac is not None else None,
        vsini=float(sme.vsini) if sme.vsini is not None else None,
    )


@router.put("/params")
async def update_params(params: StellarParams):
    """Update stellar parameters."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    sme = session.sme
    if params.teff is not None:
        sme.teff = params.teff
    if params.logg is not None:
        sme.logg = params.logg
    if params.monh is not None:
        sme.monh = params.monh
    if params.vmic is not None:
        sme.vmic = params.vmic
    if params.vmac is not None:
        sme.vmac = params.vmac
    if params.vsini is not None:
        sme.vsini = params.vsini

    return {"status": "ok"}


@router.put("/fit-settings")
async def update_fit_settings(settings: FitSettings):
    """Update which parameters to fit."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    fitparams = []
    if settings.fit_teff:
        fitparams.append("teff")
    if settings.fit_logg:
        fitparams.append("logg")
    if settings.fit_monh:
        fitparams.append("monh")
    if settings.fit_vmic:
        fitparams.append("vmic")
    if settings.fit_vmac:
        fitparams.append("vmac")
    if settings.fit_vsini:
        fitparams.append("vsini")

    session.sme.fitparameters = fitparams
    return {"status": "ok", "fitparameters": fitparams}


@router.put("/instrument")
async def update_instrument(settings: InstrumentSettings):
    """Update instrumental settings."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    if settings.ipres is not None:
        session.sme.ipres = settings.ipres
    if settings.iptype:
        session.sme.iptype = settings.iptype
    if settings.vrad is not None:
        session.sme.vrad = np.array([settings.vrad])
    if settings.snr is not None and settings.snr > 0:
        from ...iliffe_vector import Iliffe_vector
        if session.sme.spec is not None:
            session.sme.uncs = Iliffe_vector([
                np.full_like(seg, 1.0 / settings.snr) for seg in session.sme.spec
            ])

    return {"status": "ok"}


@router.put("/continuum")
async def update_continuum(settings: ContinuumSettings):
    """Update continuum settings."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    session.sme.cscale_flag = settings.cscale_flag
    session.sme.cscale_type = settings.cscale_type

    return {"status": "ok"}


@router.put("/radial-velocity")
async def update_radial_velocity(settings: RadialVelocitySettings):
    """Update radial velocity settings."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    session.sme.vrad_flag = settings.vrad_flag

    return {"status": "ok"}


@router.put("/abund-pattern")
async def update_abund_pattern(update: AbundPatternUpdate):
    """Update abundance pattern."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    from ...abund import Abund

    valid_patterns = ["asplund2021", "asplund2009", "grevesse2007", "lodders2003"]
    if update.pattern not in valid_patterns:
        raise HTTPException(status_code=400, detail=f"Invalid pattern: {update.pattern}")

    monh = session.sme.monh if session.sme.monh is not None else 0.0
    session.sme.abund = Abund(monh=monh, pattern=update.pattern)
    session.abund_pattern = update.pattern

    return {"status": "ok"}


@router.put("/wave-limits")
async def update_wave_limits(update: WaveLimitsUpdate):
    """Update wavelength limits for synthesis (single segment)."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    if update.wl_min >= update.wl_max:
        raise HTTPException(status_code=400, detail="wl_min must be less than wl_max")

    session.sme.wran = np.array([[update.wl_min, update.wl_max]])

    return {"status": "ok"}


@router.put("/wave-limits/multi")
async def update_wave_limits_multi(update: MultiSegmentWaveLimits):
    """Update wavelength limits for multiple segments."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    if not update.segments:
        raise HTTPException(status_code=400, detail="At least one segment required")

    for i, seg in enumerate(update.segments):
        if len(seg) != 2:
            raise HTTPException(status_code=400, detail=f"Segment {i} must have exactly 2 values")
        if seg[0] >= seg[1]:
            raise HTTPException(status_code=400, detail=f"Segment {i}: wl_min must be less than wl_max")

    session.sme.wran = np.array(update.segments)

    return {"status": "ok", "nseg": len(update.segments)}


NLTE_ELEMENTS = ["H", "Li", "C", "N", "O", "Na", "Mg", "Al", "Si", "K", "Ca", "Ti", "Mn", "Fe", "Cu", "Ba"]


@router.put("/nlte")
async def update_nlte(settings: NLTESettings):
    """Enable or disable NLTE for supported elements."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    if settings.enabled:
        for element in NLTE_ELEMENTS:
            try:
                session.sme.nlte.set_nlte(element)
            except Exception:
                pass
    else:
        session.sme.nlte.elements = []
        session.sme.nlte.grids = {}

    session.nlte_enabled = settings.enabled
    return {"status": "ok", "enabled": settings.enabled, "elements": list(session.sme.nlte.elements)}


@router.put("/fit-abundances")
async def update_fit_abundances(settings: AbundanceFitSettings):
    """Update which element abundances to fit."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    session.fit_abundances = settings.elements
    return {"status": "ok", "elements": settings.elements}


@router.get("/spectrum", response_model=SpectrumData)
async def get_spectrum():
    """Get spectrum data for plotting."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    sme = session.sme

    def to_list(arr):
        if arr is None:
            return None
        return [seg.tolist() for seg in arr]

    return SpectrumData(
        wave=to_list(sme.wave) or [],
        spec=to_list(sme.spec),
        synth=to_list(sme.synth),
        mask=to_list(sme.mask),
        nseg=sme.nseg if sme.wave is not None else 0,
        wran=sme.wran.tolist() if sme.wran is not None else None,
    )


@router.get("/spectrum/plot")
async def get_spectrum_plot(segment: int = 0):
    """Get Plotly JSON for spectrum plot."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    from ..plot_plotly import FinalPlot
    import plotly.io as pio

    try:
        fig = FinalPlot(session.sme, segment=segment)
        return json.loads(pio.to_json(fig.fig))
    except Exception as e:
        logger.exception("Failed to create plot")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/spectrum/mask")
async def update_mask(update: MaskUpdate):
    """Update spectrum mask in a wavelength range."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    if session.sme.mask is None or session.sme.wave is None:
        raise HTTPException(status_code=400, detail="No spectrum loaded")

    if update.segment >= len(session.sme.mask):
        raise HTTPException(status_code=400, detail=f"Invalid segment: {update.segment}")

    wave = session.sme.wave[update.segment]
    mask = session.sme.mask[update.segment]
    idx = (wave >= update.wl_min) & (wave <= update.wl_max)
    mask[idx] = update.mask_value

    return {"status": "ok", "modified_points": int(np.sum(idx))}


@router.post("/spectrum/load")
async def load_spectrum(file: UploadFile = File(...)):
    """Load observed spectrum from FITS or CSV file."""
    if session.sme is None:
        session.sme = SME_Structure()

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        if suffix == ".fits":
            from astropy.io import fits

            with fits.open(tmp_path) as hdul:
                if len(hdul) > 1 and hdul[1].data is not None:
                    data = hdul[1].data
                    if "Wavelength" in data.names and "Normalized_Flux" in data.names:
                        wave = np.array(data["Wavelength"])
                        spec = np.array(data["Normalized_Flux"])
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail="FITS table must have 'Wavelength' and 'Normalized_Flux' columns",
                        )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="FITS file must have binary table extension",
                    )
        elif suffix == ".csv":
            import pandas as pd

            df = pd.read_csv(tmp_path)
            if "Wavelength" in df.columns and "Normalized_Flux" in df.columns:
                wave = df["Wavelength"].values
                spec = df["Normalized_Flux"].values
            elif len(df.columns) >= 2:
                wave = df.iloc[:, 0].values
                spec = df.iloc[:, 1].values
            else:
                raise HTTPException(
                    status_code=400,
                    detail="CSV must have at least 2 columns (wavelength, flux)",
                )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {suffix}")

        from ...iliffe_vector import Iliffe_vector

        session.sme.wave = Iliffe_vector([wave])
        session.sme.spec = Iliffe_vector([spec])
        session.sme.mask = Iliffe_vector([np.ones_like(spec, dtype=int)])
        session.sme.wran = np.array([[wave.min(), wave.max()]])

        Path(tmp_path).unlink(missing_ok=True)

        return {
            "status": "ok",
            "message": f"Loaded spectrum from {file.filename}",
            "npoints": len(wave),
            "wl_min": float(wave.min()),
            "wl_max": float(wave.max()),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to load spectrum")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/linelists")
async def list_linelists():
    """List available built-in linelists."""
    linelists = []

    if LINELIST_DIR.exists():
        for f in sorted(LINELIST_DIR.iterdir()):
            if f.suffix.lower() in (".lin", ".vald", ".txt"):
                linelists.append({
                    "name": f.stem,
                    "filename": f.name,
                    "description": f.stem.replace("_", " "),
                    "builtin": True,
                })

    return {"linelists": linelists}


@router.post("/linelist/load-builtin")
async def load_builtin_linelist(request: BuiltinLinelistRequest):
    """Load a built-in linelist by name."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    linelist_path = None
    if LINELIST_DIR.exists():
        for ext in ["", ".lin", ".vald", ".txt"]:
            candidate = LINELIST_DIR / (request.name + ext)
            if candidate.exists():
                linelist_path = candidate
                break

    if linelist_path is None:
        raise HTTPException(status_code=404, detail=f"Linelist not found: {request.name}")

    try:
        from ...linelist.vald import ValdFile

        linelist = ValdFile(str(linelist_path))
        session.sme.linelist = linelist

        return LinelistInfo(
            name=request.name,
            nlines=len(linelist),
            wl_min=float(linelist.wlcent.min()),
            wl_max=float(linelist.wlcent.max()),
        )
    except Exception as e:
        logger.exception("Failed to load built-in linelist")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/linelist/load")
async def load_linelist(file: UploadFile = File(...)):
    """Load linelist from VALD file."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    try:
        with tempfile.NamedTemporaryFile(suffix=".lin", delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        from ...linelist.vald import ValdFile

        linelist = ValdFile(tmp_path)
        session.sme.linelist = linelist

        Path(tmp_path).unlink(missing_ok=True)

        return LinelistInfo(
            name=file.filename,
            nlines=len(linelist),
            wl_min=float(linelist.wlcent.min()),
            wl_max=float(linelist.wlcent.max()),
        )
    except Exception as e:
        logger.exception("Failed to load linelist")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/linelist")
async def get_linelist():
    """Get current linelist info."""
    if session.sme is None or session.sme.linelist is None:
        return {"loaded": False}

    ll = session.sme.linelist
    return {
        "loaded": True,
        "nlines": len(ll),
        "wl_min": float(ll.wlcent.min()),
        "wl_max": float(ll.wlcent.max()),
    }


@router.post("/synthesize")
async def synthesize(request: SynthesizeRequest = None):
    """Synthesize spectrum."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    if session.sme.linelist is None or len(session.sme.linelist) == 0:
        raise HTTPException(status_code=400, detail="No linelist loaded")

    try:
        sme = session.sme
        segments = request.segments if request and request.segments else "all"
        session.sme = synthesize_spectrum(sme, segments=segments)
        return {"status": "ok", "message": "Synthesis complete"}
    except Exception as e:
        logger.exception("Synthesis failed")
        raise HTTPException(status_code=500, detail=str(e))


def _run_solve(sme, fitparams):
    """Run solver in background thread."""
    try:
        solver = SME_Solver()
        session.solver = solver
        session.sme = solver.solve(sme, fitparams)
        session.solve_done = True
    except Exception as e:
        logger.exception("Solve failed")
        session.solve_error = str(e)
        session.solve_done = True


@router.post("/solve")
async def solve(request: SolveRequest):
    """Start parameter fitting."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    if session.sme.linelist is None or len(session.sme.linelist) == 0:
        raise HTTPException(status_code=400, detail="No linelist loaded")

    if session.sme.spec is None:
        raise HTTPException(status_code=400, detail="No observed spectrum loaded")

    if not request.parameters and not session.fit_abundances:
        raise HTTPException(status_code=400, detail="No parameters to fit")

    fitparams = list(request.parameters)
    for elem in session.fit_abundances:
        fitparams.append(f"abund {elem}")

    session.solve_cancelled = False
    session.solve_done = False
    session.solve_error = None
    session.solve_progress = []

    thread = threading.Thread(
        target=_run_solve, args=(session.sme, fitparams)
    )
    session.solve_task = thread
    thread.start()

    return {"status": "ok", "message": "Solve started"}


@router.get("/solve/stream")
async def solve_stream():
    """Stream solve progress via Server-Sent Events."""

    async def event_generator():
        while True:
            if session.solve_cancelled:
                yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                break

            if session.solve_error:
                yield f"data: {json.dumps({'type': 'error', 'message': session.solve_error})}\n\n"
                break

            if session.solve_done:
                result = {}
                if session.sme and session.sme.fitresults:
                    fr = session.sme.fitresults
                    result = {
                        "type": "done",
                        "parameters": list(fr.parameters) if fr.parameters is not None else [],
                        "values": [float(v) for v in fr.values] if fr.values is not None else [],
                        "uncertainties": [float(u) for u in fr.uncertainties] if fr.uncertainties is not None else [],
                        "chisq": float(fr.chisq) if fr.chisq is not None else None,
                        "iterations": int(fr.iterations) if fr.iterations is not None else 0,
                    }
                else:
                    result = {"type": "done"}
                yield f"data: {json.dumps(result)}\n\n"
                break

            if session.solver:
                yield f"data: {json.dumps({'type': 'progress', 'iteration': session.solver.iteration})}\n\n"

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/solve/cancel")
async def cancel_solve():
    """Cancel running solve."""
    session.solve_cancelled = True
    return {"status": "ok", "message": "Solve cancelled"}


@router.get("/fit-results", response_model=Optional[FitResult])
async def get_fit_results():
    """Get fit results."""
    if session.sme is None or session.sme.fitresults is None:
        return None

    fr = session.sme.fitresults
    if fr.parameters is None or len(fr.parameters) == 0:
        return None
    return FitResult(
        parameters=list(fr.parameters) if fr.parameters is not None else [],
        values=[float(v) for v in fr.values] if fr.values is not None else [],
        uncertainties=[float(u) for u in fr.uncertainties] if fr.uncertainties is not None else [],
        chisq=float(fr.chisq) if fr.chisq is not None else 0.0,
        iterations=int(fr.iterations) if fr.iterations is not None else 0,
    )


def _run_mcmc(sme, params, nwalkers, nsteps, nburn):
    """Run MCMC in background thread."""
    from ...solve import SME_MCMC

    try:
        mcmc = SME_MCMC(sme, nwalkers=nwalkers, nsteps=nsteps, nburn=nburn)
        session.mcmc_runner = mcmc
        results = mcmc.run(params, progress=False)
        session.sme = mcmc.sme
        session.mcmc_results = results
        session.mcmc_done = True
    except Exception as e:
        logger.exception("MCMC failed")
        session.mcmc_error = str(e)
        session.mcmc_done = True


@router.post("/mcmc")
async def run_mcmc(request: MCMCRequest):
    """Start MCMC parameter estimation."""
    if session.sme is None:
        raise HTTPException(status_code=400, detail="No session loaded")

    if session.sme.linelist is None or len(session.sme.linelist) == 0:
        raise HTTPException(status_code=400, detail="No linelist loaded")

    if session.sme.spec is None:
        raise HTTPException(status_code=400, detail="No observed spectrum loaded")

    params = list(request.parameters)
    for elem in session.fit_abundances:
        params.append(f"abund {elem}")

    if not params:
        raise HTTPException(status_code=400, detail="No parameters to sample")

    session.mcmc_done = False
    session.mcmc_error = None
    session.mcmc_results = None
    session.mcmc_runner = None

    thread = threading.Thread(
        target=_run_mcmc,
        args=(session.sme, params, request.nwalkers, request.nsteps, request.nburn),
    )
    session.mcmc_task = thread
    thread.start()

    return {"status": "ok", "message": "MCMC started"}


@router.get("/mcmc/stream")
async def mcmc_stream():
    """Stream MCMC progress via Server-Sent Events."""

    async def event_generator():
        while True:
            if session.mcmc_error:
                yield f"data: {json.dumps({'type': 'error', 'message': session.mcmc_error})}\n\n"
                break

            if session.mcmc_done:
                result = {"type": "done"}
                if session.mcmc_results:
                    result.update({
                        "parameters": session.mcmc_results.get("parameters", []),
                        "values": session.mcmc_results.get("values", []),
                        "uncertainties": session.mcmc_results.get("uncertainties", []),
                        "uncertainties_low": session.mcmc_results.get("uncertainties_low", []),
                        "uncertainties_high": session.mcmc_results.get("uncertainties_high", []),
                        "acceptance_fraction": session.mcmc_results.get("acceptance_fraction", 0),
                    })
                yield f"data: {json.dumps(result)}\n\n"
                break

            if session.mcmc_runner:
                yield f"data: {json.dumps({'type': 'progress', 'iteration': session.mcmc_runner.iteration})}\n\n"

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/mcmc/results", response_model=Optional[MCMCResult])
async def get_mcmc_results():
    """Get MCMC results."""
    if session.mcmc_results is None:
        return None

    return MCMCResult(
        parameters=session.mcmc_results.get("parameters", []),
        values=session.mcmc_results.get("values", []),
        uncertainties=session.mcmc_results.get("uncertainties", []),
        uncertainties_low=session.mcmc_results.get("uncertainties_low", []),
        uncertainties_high=session.mcmc_results.get("uncertainties_high", []),
        acceptance_fraction=session.mcmc_results.get("acceptance_fraction", 0),
    )


@router.get("/logs/stream")
async def logs_stream():
    """Stream log messages via Server-Sent Events."""

    async def event_generator():
        index = len(session.log_entries)
        while True:
            while index < len(session.log_entries):
                entry = session.log_entries[index]
                yield f"data: {json.dumps(entry)}\n\n"
                index += 1
            await asyncio.sleep(0.3)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

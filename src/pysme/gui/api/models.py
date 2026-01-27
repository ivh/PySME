# -*- coding: utf-8 -*-
"""Pydantic models for API request/response validation."""

from typing import Optional

from pydantic import BaseModel, Field


class StellarParams(BaseModel):
    """Stellar parameters for synthesis."""

    teff: Optional[float] = Field(None, ge=2500, le=50000, description="Effective temperature in K")
    logg: Optional[float] = Field(None, ge=-1, le=6, description="Surface gravity in log(cgs)")
    monh: Optional[float] = Field(None, ge=-5, le=1, description="Metallicity [M/H]")
    vmic: Optional[float] = Field(None, ge=0, le=20, description="Microturbulence in km/s")
    vmac: Optional[float] = Field(None, ge=0, le=50, description="Macroturbulence in km/s")
    vsini: Optional[float] = Field(None, ge=0, le=500, description="Projected rotation in km/s")


class FitSettings(BaseModel):
    """Settings for parameter fitting."""

    fit_teff: bool = False
    fit_logg: bool = False
    fit_monh: bool = False
    fit_vmic: bool = False
    fit_vmac: bool = False
    fit_vsini: bool = False


class InstrumentSettings(BaseModel):
    """Instrumental settings."""

    ipres: Optional[float] = Field(None, ge=0, le=1000000, description="Resolving power")
    iptype: str = Field("gauss", description="Instrumental profile type")


class ContinuumSettings(BaseModel):
    """Continuum correction settings."""

    cscale_flag: str = Field("linear", description="Continuum scaling mode")
    cscale_type: str = Field("match", description="Continuum fitting type")


class RadialVelocitySettings(BaseModel):
    """Radial velocity settings."""

    vrad_flag: str = Field("whole", description="RV correction mode")


class SessionState(BaseModel):
    """Current session state."""

    has_observation: bool = False
    has_synthetic: bool = False
    has_linelist: bool = False
    nseg: int = 0
    filename: Optional[str] = None
    stellar_params: StellarParams = Field(default_factory=StellarParams)
    fit_settings: FitSettings = Field(default_factory=FitSettings)
    instrument: InstrumentSettings = Field(default_factory=InstrumentSettings)
    continuum: ContinuumSettings = Field(default_factory=ContinuumSettings)
    radial_velocity: RadialVelocitySettings = Field(default_factory=RadialVelocitySettings)
    abund_pattern: str = "asplund2021"
    wran: Optional[list[list[float]]] = None


class AbundPatternUpdate(BaseModel):
    """Update abundance pattern."""

    pattern: str = Field(..., description="Abundance pattern name")


class WaveLimitsUpdate(BaseModel):
    """Update wavelength limits."""

    wl_min: float = Field(..., description="Minimum wavelength in Angstrom")
    wl_max: float = Field(..., description="Maximum wavelength in Angstrom")


class SpectrumData(BaseModel):
    """Spectrum data for plotting."""

    wave: list[list[float]]
    spec: Optional[list[list[float]]] = None
    synth: Optional[list[list[float]]] = None
    mask: Optional[list[list[int]]] = None
    nseg: int = 0
    wran: Optional[list[list[float]]] = None


class FitResult(BaseModel):
    """Fitting results."""

    parameters: list[str]
    values: list[float]
    uncertainties: list[float]
    chisq: float
    iterations: int


class SynthesizeRequest(BaseModel):
    """Request to synthesize spectrum."""

    segments: Optional[list[int]] = None


class SolveRequest(BaseModel):
    """Request to solve/fit parameters."""

    parameters: list[str]
    segments: Optional[list[int]] = None


class LinelistInfo(BaseModel):
    """Linelist information."""

    name: str
    nlines: int
    wl_min: float
    wl_max: float


class ErrorResponse(BaseModel):
    """Error response."""

    detail: str

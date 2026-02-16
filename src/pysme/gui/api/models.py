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
    vrad: Optional[float] = Field(None, description="Radial velocity in km/s")
    snr: Optional[float] = Field(None, ge=1, description="Signal-to-noise ratio")


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
    nlte_enabled: bool = False
    fit_abundances: list[str] = Field(default_factory=list)
    available_elements: list[str] = Field(default_factory=list)


class NLTESettings(BaseModel):
    """NLTE settings."""

    enabled: bool = Field(..., description="Enable NLTE for supported elements")


class AbundPatternUpdate(BaseModel):
    """Update abundance pattern."""

    pattern: str = Field(..., description="Abundance pattern name")


class WaveLimitsUpdate(BaseModel):
    """Update wavelength limits."""

    wl_min: float = Field(..., description="Minimum wavelength in Angstrom")
    wl_max: float = Field(..., description="Maximum wavelength in Angstrom")


class MultiSegmentWaveLimits(BaseModel):
    """Update wavelength limits for multiple segments."""

    segments: list[list[float]] = Field(..., description="List of [wl_min, wl_max] pairs")


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


class AbundanceFitSettings(BaseModel):
    """Settings for fitting element abundances."""

    elements: list[str] = Field(default_factory=list, description="Elements to fit abundances for")


class MaskUpdate(BaseModel):
    """Update spectrum mask in a wavelength range."""

    segment: int = Field(0, ge=0, description="Segment index")
    wl_min: float = Field(..., description="Minimum wavelength")
    wl_max: float = Field(..., description="Maximum wavelength")
    mask_value: int = Field(..., ge=0, le=2, description="Mask value: 0=bad, 1=line, 2=continuum")


class MCMCRequest(BaseModel):
    """Request to run MCMC parameter estimation."""

    parameters: list[str] = Field(..., description="Parameters to sample")
    nwalkers: int = Field(32, ge=4, description="Number of MCMC walkers")
    nsteps: int = Field(500, ge=10, description="Number of MCMC steps")
    nburn: int = Field(100, ge=0, description="Number of burn-in steps")


class MCMCResult(BaseModel):
    """MCMC fitting results."""

    parameters: list[str]
    values: list[float]
    uncertainties: list[float]
    uncertainties_low: list[float]
    uncertainties_high: list[float]
    acceptance_fraction: float


class LinelistInfo(BaseModel):
    """Linelist information."""

    name: str
    nlines: int
    wl_min: float
    wl_max: float


class BuiltinLinelistRequest(BaseModel):
    """Request to load a built-in linelist."""

    name: str = Field(..., description="Name of the built-in linelist file")


class ErrorResponse(BaseModel):
    """Error response."""

    detail: str

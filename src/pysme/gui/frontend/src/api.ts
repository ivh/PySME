// API client for PySME GUI

const BASE_URL = '/api'

export interface StellarParams {
  teff: number | null
  logg: number | null
  monh: number | null
  vmic: number | null
  vmac: number | null
  vsini: number | null
}

export interface FitSettings {
  fit_teff: boolean
  fit_logg: boolean
  fit_monh: boolean
  fit_vmic: boolean
  fit_vmac: boolean
  fit_vsini: boolean
}

export interface InstrumentSettings {
  ipres: number | null
  iptype: string
  vrad: number | null
  snr: number | null
}

export interface ContinuumSettings {
  cscale_flag: string
  cscale_type: string
}

export interface RadialVelocitySettings {
  vrad_flag: string
}

export interface SessionState {
  has_observation: boolean
  has_synthetic: boolean
  has_linelist: boolean
  nseg: number
  filename: string | null
  stellar_params: StellarParams
  fit_settings: FitSettings
  instrument: InstrumentSettings
  continuum: ContinuumSettings
  radial_velocity: RadialVelocitySettings
  abund_pattern: string
  wran: number[][] | null
  nlte_enabled: boolean
  fit_abundances: string[]
  available_elements: string[]
}

export interface SpectrumData {
  wave: number[][]
  spec: number[][] | null
  synth: number[][] | null
  mask: number[][] | null
  nseg: number
  wran: number[][] | null
}

export interface FitResult {
  parameters: string[]
  values: number[]
  uncertainties: number[]
  chisq: number
  iterations: number
}

export interface MCMCResult {
  parameters: string[]
  values: number[]
  uncertainties: number[]
  uncertainties_low: number[]
  uncertainties_high: number[]
  acceptance_fraction: number
}

export interface LinelistInfo {
  name: string
  nlines: number
  wl_min: number
  wl_max: number
}

export interface BuiltinLinelist {
  name: string
  filename: string
  description: string
  builtin: boolean
}

export interface LogEntry {
  type: string
  level: string
  message: string
  time: number
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${BASE_URL}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || 'Request failed')
  }

  return response.json()
}

export const api = {
  // Session
  async newSession(): Promise<{ status: string; message: string }> {
    return request('/session/new', { method: 'POST' })
  },

  async loadSession(file: File): Promise<{ status: string; message: string; nseg: number }> {
    const formData = new FormData()
    formData.append('file', file)
    const response = await fetch(`${BASE_URL}/session/load`, {
      method: 'POST',
      body: formData,
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }))
      throw new Error(error.detail || 'Upload failed')
    }
    return response.json()
  },

  async getSession(): Promise<SessionState> {
    return request('/session')
  },

  async loadTestSpectrum(): Promise<{ status: string; message: string }> {
    return request('/session/load-test', { method: 'POST' })
  },

  async loadSolarSpectrum(): Promise<{ status: string; message: string }> {
    return request('/session/load-solar', { method: 'POST' })
  },

  async saveSession(): Promise<Blob> {
    const response = await fetch(`${BASE_URL}/session/save`, { method: 'POST' })
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }))
      throw new Error(error.detail || 'Save failed')
    }
    return response.blob()
  },

  // Parameters
  async getParams(): Promise<StellarParams> {
    return request('/params')
  },

  async updateParams(params: Partial<StellarParams>): Promise<{ status: string }> {
    return request('/params', {
      method: 'PUT',
      body: JSON.stringify(params),
    })
  },

  async updateFitSettings(settings: FitSettings): Promise<{ status: string; fitparameters: string[] }> {
    return request('/fit-settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    })
  },

  async updateInstrument(settings: Partial<InstrumentSettings>): Promise<{ status: string }> {
    return request('/instrument', {
      method: 'PUT',
      body: JSON.stringify(settings),
    })
  },

  async updateContinuum(settings: Partial<ContinuumSettings>): Promise<{ status: string }> {
    return request('/continuum', {
      method: 'PUT',
      body: JSON.stringify(settings),
    })
  },

  async updateRadialVelocity(settings: Partial<RadialVelocitySettings>): Promise<{ status: string }> {
    return request('/radial-velocity', {
      method: 'PUT',
      body: JSON.stringify(settings),
    })
  },

  async updateAbundPattern(pattern: string): Promise<{ status: string }> {
    return request('/abund-pattern', {
      method: 'PUT',
      body: JSON.stringify({ pattern }),
    })
  },

  async updateWaveLimits(wl_min: number, wl_max: number): Promise<{ status: string }> {
    return request('/wave-limits', {
      method: 'PUT',
      body: JSON.stringify({ wl_min, wl_max }),
    })
  },

  async updateWaveLimitsMulti(segments: number[][]): Promise<{ status: string; nseg: number }> {
    return request('/wave-limits/multi', {
      method: 'PUT',
      body: JSON.stringify({ segments }),
    })
  },

  async updateNLTE(enabled: boolean): Promise<{ status: string; enabled: boolean; elements: string[] }> {
    return request('/nlte', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    })
  },

  async updateFitAbundances(elements: string[]): Promise<{ status: string; elements: string[] }> {
    return request('/fit-abundances', {
      method: 'PUT',
      body: JSON.stringify({ elements }),
    })
  },

  // Spectrum
  async getSpectrum(): Promise<SpectrumData> {
    return request('/spectrum')
  },

  async getSpectrumPlot(segment: number = 0): Promise<object> {
    return request(`/spectrum/plot?segment=${segment}`)
  },

  async updateMask(segment: number, wl_min: number, wl_max: number, mask_value: number): Promise<{ status: string; modified_points: number }> {
    return request('/spectrum/mask', {
      method: 'PUT',
      body: JSON.stringify({ segment, wl_min, wl_max, mask_value }),
    })
  },

  async loadSpectrum(file: File): Promise<{ status: string; message: string; npoints: number; wl_min: number; wl_max: number }> {
    const formData = new FormData()
    formData.append('file', file)
    const response = await fetch(`${BASE_URL}/spectrum/load`, {
      method: 'POST',
      body: formData,
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }))
      throw new Error(error.detail || 'Upload failed')
    }
    return response.json()
  },

  // Linelist
  async getLinelist(): Promise<{ loaded: boolean; nlines?: number; wl_min?: number; wl_max?: number }> {
    return request('/linelist')
  },

  async loadLinelist(file: File): Promise<LinelistInfo> {
    const formData = new FormData()
    formData.append('file', file)
    const response = await fetch(`${BASE_URL}/linelist/load`, {
      method: 'POST',
      body: formData,
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }))
      throw new Error(error.detail || 'Upload failed')
    }
    return response.json()
  },

  async getAvailableLinelists(): Promise<{ linelists: BuiltinLinelist[] }> {
    return request('/linelists')
  },

  async loadBuiltinLinelist(name: string): Promise<LinelistInfo> {
    return request('/linelist/load-builtin', {
      method: 'POST',
      body: JSON.stringify({ name }),
    })
  },

  // Logs
  logsStream(): EventSource {
    return new EventSource(`${BASE_URL}/logs/stream`)
  },

  // Synthesis and solving
  async synthesize(segments?: number[]): Promise<{ status: string; message: string }> {
    return request('/synthesize', {
      method: 'POST',
      body: JSON.stringify({ segments }),
    })
  },

  async solve(parameters: string[], segments?: number[]): Promise<{ status: string; message: string }> {
    return request('/solve', {
      method: 'POST',
      body: JSON.stringify({ parameters, segments }),
    })
  },

  solveStream(): EventSource {
    return new EventSource(`${BASE_URL}/solve/stream`)
  },

  async cancelSolve(): Promise<{ status: string; message: string }> {
    return request('/solve/cancel', { method: 'POST' })
  },

  // Kills whatever is running (synthesis, fit or MCMC)
  async cancelJob(): Promise<{ status: string; message: string }> {
    return request('/cancel', { method: 'POST' })
  },

  async getFitResults(): Promise<FitResult | null> {
    return request('/fit-results')
  },

  // MCMC
  async runMCMC(
    parameters: string[],
    nwalkers: number = 32,
    nsteps: number = 500,
    nburn: number = 100
  ): Promise<{ status: string; message: string }> {
    return request('/mcmc', {
      method: 'POST',
      body: JSON.stringify({ parameters, nwalkers, nsteps, nburn }),
    })
  },

  mcmcStream(): EventSource {
    return new EventSource(`${BASE_URL}/mcmc/stream`)
  },

  async getMCMCResults(): Promise<MCMCResult | null> {
    return request('/mcmc/results')
  },
}

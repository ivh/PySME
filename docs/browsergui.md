# PySME Local Web GUI

## Overview

A local web GUI for PySME that ships with the package. Users run `pysme gui` and interact via browser at `localhost:8000`.

## Architecture

```
User runs: pysme gui
           ↓
    ┌──────────────────────────────────────────────┐
    │  FastAPI Server (localhost:8000)             │
    │  ├── /api/* endpoints → PySME calls          │
    │  └── /* → Vue SPA (bundled static files)     │
    └──────────────────────────────────────────────┘
           ↓
    Browser opens automatically
```

**Key decisions:**
- **FastAPI** over Flask: async support, automatic OpenAPI docs, Pydantic validation
- **Vue 3 + Vite**: modern, fast builds, ships as static files (no Node.js runtime needed)
- **Plotly.js**: already used by PySME's `plot_plotly.py`, good for interactive spectra
- **Single-user, synchronous**: no Celery/job queue (unlike websme)

## Current Status

### Completed (v0.1)

- [x] **Backend Foundation**
  - FastAPI server with CORS support
  - Session management (in-memory SME_Structure)
  - CLI entry point: `pysme gui [--host] [--port] [--no-browser]`
  - Static file serving for built Vue app

- [x] **API Endpoints**
  - Session: new, load, save, get state
  - Parameters: get/update stellar params, fit settings, instrument, continuum, RV
  - Abundance pattern selection (Asplund 2021/2009, Grevesse 2007, Lodders 2003)
  - Wavelength limits
  - Spectrum: load (FITS/CSV), get data, get Plotly plot
  - Linelist: load VALD files
  - Synthesis: run synthesis
  - Solving: run with SSE progress streaming, cancel

- [x] **Frontend (Vue 3 + Vite)**
  - File controls (new session, load .sme, load spectrum, load linelist, save)
  - Interactive spectrum plot with Plotly.js
  - Parameter form with websme-style layout:
    - Instr. specs & Source (resolution, SNR, Vrad)
    - Stellar parameters with fit checkboxes (Teff, logg, monh, Vmic, Vmac, Vsini)
    - Solar ref. composition (radio buttons)
    - Linelist upload
    - Wavelength limits
    - Options (NLTE, retain continuum)
  - Fit results display (chi-squared, parameters with uncertainties)
  - Status messages and error handling

- [x] **Build & Distribution**
  - Frontend builds to `gui/static/` via Vite
  - pyproject.toml: `[project.scripts]` entry point, `[project.optional-dependencies] gui`
  - .gitignore for node_modules

### Not Yet Implemented

- [ ] NLTE toggle (UI exists, backend integration pending)
- [ ] SNR handling (UI exists, not used by synthesis yet)
- [ ] Vrad from form (UI exists, needs to update sme.vrad)
- [ ] Multi-segment wavelength limits
- [ ] Mask editing in plot
- [ ] Element abundance derivation
- [ ] Built-in linelists (currently user upload only)
- [ ] Precomputed grid mode
- [ ] MCMC fitting

## File Structure

```
src/pysme/
├── __main__.py              # CLI with 'gui' subcommand
├── gui/
│   ├── __init__.py
│   ├── server.py            # FastAPI app + CLI command
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py        # API endpoints
│   │   └── models.py        # Pydantic request/response models
│   ├── frontend/            # Vue source (dev only)
│   │   ├── package.json
│   │   ├── vite.config.ts
│   │   ├── tsconfig.json
│   │   ├── index.html
│   │   └── src/
│   │       ├── main.ts
│   │       ├── App.vue
│   │       ├── api.ts
│   │       └── components/
│   │           ├── FileControls.vue
│   │           ├── ParameterForm.vue
│   │           ├── SpectrumPlot.vue
│   │           └── FitResults.vue
│   ├── static/              # Built Vue app (shipped with package)
│   │   ├── index.html
│   │   └── assets/
│   ├── plot_plotly.py       # (existing)
│   └── plot_pyplot.py       # (existing)
```

## API Endpoints

### Session Management
```
POST /api/session/new              → Create empty SME_Structure
POST /api/session/load             → Upload .sme file
GET  /api/session                  → Get current state
POST /api/session/save             → Download .sme file
```

### Parameters
```
GET  /api/params                   → Get stellar parameters
PUT  /api/params                   → Update parameters
PUT  /api/fit-settings             → Update which params to fit
PUT  /api/instrument               → Update resolution, iptype
PUT  /api/continuum                → Update cscale_flag, cscale_type
PUT  /api/radial-velocity          → Update vrad_flag
PUT  /api/abund-pattern            → Update abundance reference
PUT  /api/wave-limits              → Update wavelength range
```

### Spectrum
```
POST /api/spectrum/load            → Upload observed spectrum (FITS/CSV)
GET  /api/spectrum                 → Get wave/spec/synth/mask arrays
GET  /api/spectrum/plot            → Get Plotly JSON figure
```

### Linelist
```
GET  /api/linelist                 → Get linelist info
POST /api/linelist/load            → Upload VALD linelist
```

### Synthesis & Fitting
```
POST /api/synthesize               → Run synthesis
POST /api/solve                    → Start parameter fitting
GET  /api/solve/stream             → SSE for fit progress
POST /api/solve/cancel             → Cancel running fit
GET  /api/fit-results              → Get fit results
```

## Usage

### Install with GUI support
```bash
uv sync  # GUI deps included in dev group
# or
pip install pysme-astro[gui]
```

### Start the GUI
```bash
pysme gui                    # Opens browser automatically
pysme gui --no-browser       # Don't open browser
pysme gui --port 8080        # Custom port
```

### Development
```bash
# Terminal 1: Run backend
uv run pysme gui --no-browser

# Terminal 2: Run frontend dev server with hot reload
cd src/pysme/gui/frontend
npm install
npm run dev
# Frontend at localhost:5173, proxies /api to localhost:8000
```

### Build frontend for distribution
```bash
cd src/pysme/gui/frontend
npm run build  # Outputs to ../static/
```

## Dependencies

Runtime (in `[project.optional-dependencies] gui`):
- fastapi>=0.100
- uvicorn>=0.23
- python-multipart>=0.0.6

Frontend (dev only, not shipped):
- vue ^3.5
- vite ^6.0
- plotly.js-dist-min ^2.35
- typescript ~5.6

## Reference

The UI design is inspired by websme (https://websme.chetec-infra.eu/). Reference materials are stored in `docs/websme-reference/`.

# Browser/WASM Feasibility for PySME

Assessment of running PySME's spectral synthesis entirely in the browser,
inspired by [viper-web](https://github.com/ivh/viper-web) which does this for
pyodine using Pyodide.

## Why viper-web was easy

Pyodine is pure Python + numpy/scipy. Pyodide ships those pre-compiled, so
viper-web is just static files served from a CDN — zero native compilation, zero
build complexity.

## The smelib native code

PySME's core is `smelib`: ~8.5K lines of C++ and ~47K lines of Fortran 77.

**Good news — it's remarkably WASM-friendly:**

- **No external dependencies.** Bundles its own BLAS/LAPACK routines. No
  OpenBLAS, MKL, or system LAPACK needed.
- **Pure computation.** No threads, no sockets, no system calls, no dynamic
  library loading.
- **Read-only file I/O.** Data files (~10 MB) are binary lookup tables read once
  at init. Easily bundled via Emscripten `--embed-file` or fetched on demand.
- **No COMMON blocks** in the Fortran — data passed via arguments.
- **Fixed-form Fortran 77** — the most widely supported dialect for
  cross-compilation.

**The main challenge is the Fortran-to-WASM toolchain.** Emscripten has
`emfortran` (flang/LLVM-based), but it's less mature than `emcc` for C/C++.

## What the native library does (and doesn't do)

The Fortran/C++ code handles:
- Radiative transfer (the main `Transf()` call)
- Line + continuum opacity calculation
- Ionization equilibrium (Saha equations)
- Line central depths

It does **not** handle broadening, atmosphere interpolation, RV/continuum
fitting, or NLTE coefficient interpolation — those are all Python.

## The Python layer (~18.7K lines)

| Category | Lines | Description |
|---|---|---|
| Glue/IO | ~3,900 | File readers (VALD, MARCS, Kurucz), persistence, plotting, web GUI |
| Orchestration | ~5,200 | Data containers, native lib wrappers, call sequencing |
| **Real computation** | **~1,800** | Numerical work in numpy/scipy |
| Other | ~7,800 | Config, utilities, linelist management |

### The ~1,800 lines of real computation

These sit between the UI and the native library and cannot be skipped:

1. **Broadening** (~565 lines) — rotational (vsini), macroturbulence, and
   instrumental profile convolution. Uses `scipy.ndimage.convolve`,
   `scipy.interpolate.CubicSpline`.

2. **Atmosphere interpolation** (~975 lines) — interpolating model atmospheres
   in Teff/logg/[M/H] space. A shift-and-fit algorithm using
   `scipy.optimize.curve_fit` and `scipy.interpolate.interp1d`. Runs 8 pairwise
   model interpolations per synthesis.

3. **RV + continuum fitting** (~300 lines) — cross-correlation via
   `scipy.signal.correlate`, least-squares RV refinement, polynomial/spline
   continuum normalization.

4. **NLTE interpolation** (~200 lines) — multi-dimensional interpolation of
   departure coefficient grids.

## Approaches considered

### 1. Pyodide + Emscripten (keep Python in browser)

Compile smelib as a Pyodide package. The Python side runs in Pyodide and calls
`_smelib` as it does natively.

- **Pro:** Minimal porting effort, all Python computation preserved.
- **Con:** ~50 MB download, slow startup, immature `emfortran` toolchain.

### 2. Standalone WASM + JS frontend (recommended)

Compile smelib to a standalone `.wasm` module, export the C functions directly,
call them from JavaScript. Rewrite the ~1,800 lines of Python computation in
JS/TS.

- **Pro:** Small payload (~10-15 MB WASM + data), fast startup, stays in the web
  ecosystem, debuggable in browser devtools.
- **Con:** Must port computation to JS/TS.

### 3. Move Python computation into the C library

Rewrite the ~1,800 lines of scipy-based computation in C and compile it all
into one WASM module.

- **Pro:** JS layer becomes a thin UI shell.
- **Con:** Reimplements a mini-scipy in C (convolution, splines, LM solver,
  constrained curve fitting). Creates maintenance burden — the native Python
  package still needs the Python version. Harder to debug and tinker with for
  scientists. Not recommended unless specific pieces become JS performance
  bottlenecks.

## Recommended approach

**Option 2: standalone WASM + JS/TS frontend.**

### Fortran compilation strategy

Use **f2c** to transpile the Fortran 77 to C, then compile everything with
`emcc`. This sidesteps the immature `emfortran` toolchain entirely. The F77 code
is straightforward and well-suited to f2c.

### Architecture

```
Native PySME:    Python  -->  _smelib (C++/Fortran)
Web PySME:       JS/TS   -->  smelib.wasm (same C++/Fortran via f2c + emcc)
```

### JS/TS computation layer

The ~1,800 lines of Python computation port naturally to JS/TS:

| Task | Difficulty | JS ecosystem |
|---|---|---|
| Convolution | Easy | Typed arrays + direct kernel or FFT |
| Cubic spline interpolation | Easy | Small libraries exist |
| Cross-correlation | Easy | FFT-based |
| Least-squares fitting | Medium | `ml-levenberg-marquardt` or similar |
| Atmosphere interpolation | Medium-hard | ~975 lines, self-contained, port directly |

### Data files

The ~10 MB of binary lookup tables can be:
- Bundled into the WASM module via `--embed-file` (simplest)
- Fetched on demand and cached in the browser (better UX for repeat visits)

### What would NOT work well in browser

Running the full MCMC fitting loop (emcee) would be painfully slow. But for
interactive "tweak parameters, see spectrum" use cases — which is what the web
GUI targets — single synthesis calls should be fast enough in WASM.

## Estimated effort

- WASM compilation of smelib (f2c + emcc): small project, mostly build system work
- JS/TS computation layer (~1,800 lines): moderate, a few weeks
- JS/TS UI + glue (replacing Flask API): partly done by existing Vue frontend
- Integration + testing: moderate

Not a weekend hack, but not a multi-month effort either.

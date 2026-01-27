<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api, type SessionState, type StellarParams, type FitSettings, type FitResult, type MCMCResult, type InstrumentSettings, type ContinuumSettings } from './api'
import SpectrumPlot from './components/SpectrumPlot.vue'
import ParameterForm from './components/ParameterForm.vue'
import FileControls from './components/FileControls.vue'
import FitResults from './components/FitResults.vue'

const session = ref<SessionState | null>(null)
const loading = ref(false)
const synthesizing = ref(false)
const solving = ref(false)
const error = ref<string | null>(null)
const status = ref<string | null>(null)
const fitResults = ref<FitResult | null>(null)
const mcmcResults = ref<MCMCResult | null>(null)
const plotKey = ref(0)
const forwardMode = ref(false)
const runningMCMC = ref(false)

const hasData = computed(() => session.value?.has_observation || session.value?.has_synthetic)
const canSynthesize = computed(() => session.value?.has_linelist)
const canSolve = computed(() => session.value?.has_observation && session.value?.has_linelist)

const waveRange = computed<[number, number] | null>(() => {
  if (session.value?.wran && session.value.wran.length > 0) {
    const allMin = Math.min(...session.value.wran.map(r => r[0]))
    const allMax = Math.max(...session.value.wran.map(r => r[1]))
    return [allMin, allMax]
  }
  return null
})

async function refreshSession() {
  try {
    session.value = await api.getSession()
    fitResults.value = await api.getFitResults()
    mcmcResults.value = await api.getMCMCResults()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to refresh session'
  }
}

async function handleNewSession() {
  loading.value = true
  error.value = null
  try {
    await api.newSession()
    await refreshSession()
    plotKey.value++
    status.value = 'New session created'
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to create session'
  } finally {
    loading.value = false
  }
}

async function handleFileLoaded() {
  await refreshSession()
  plotKey.value++
  status.value = 'File loaded successfully'
}

async function handleParamsChanged(params: Partial<StellarParams>) {
  try {
    await api.updateParams(params)
    await refreshSession()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to update parameters'
  }
}

async function handleFitSettingsChanged(settings: FitSettings) {
  try {
    await api.updateFitSettings(settings)
    await refreshSession()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to update fit settings'
  }
}

async function handleInstrumentChanged(settings: Partial<InstrumentSettings>) {
  try {
    await api.updateInstrument(settings)
    await refreshSession()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to update instrument settings'
  }
}

async function handleContinuumChanged(settings: Partial<ContinuumSettings>) {
  try {
    await api.updateContinuum(settings)
    await refreshSession()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to update continuum settings'
  }
}

async function handleAbundPatternChanged(pattern: string) {
  try {
    await api.updateAbundPattern(pattern)
    await refreshSession()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to update abundance pattern'
  }
}

async function handleWaveLimitsChanged(limits: { wl_min: number; wl_max: number }) {
  try {
    await api.updateWaveLimits(limits.wl_min, limits.wl_max)
    await refreshSession()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to update wavelength limits'
  }
}

async function handleWaveLimitsMultiChanged(segments: number[][]) {
  try {
    await api.updateWaveLimitsMulti(segments)
    await refreshSession()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to update wavelength segments'
  }
}

async function handleNlteChanged(enabled: boolean) {
  try {
    await api.updateNLTE(enabled)
    await refreshSession()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to update NLTE settings'
  }
}

async function handleFitAbundancesChanged(elements: string[]) {
  try {
    await api.updateFitAbundances(elements)
    await refreshSession()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to update fit abundances'
  }
}

async function handleSynthesize() {
  synthesizing.value = true
  error.value = null
  status.value = 'Synthesizing spectrum...'
  try {
    await api.synthesize()
    await refreshSession()
    plotKey.value++
    status.value = 'Synthesis complete'
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Synthesis failed'
    status.value = null
  } finally {
    synthesizing.value = false
  }
}

async function handleSolve() {
  if (!session.value) return

  const fitParams: string[] = []
  const settings = session.value.fit_settings
  if (settings.fit_teff) fitParams.push('teff')
  if (settings.fit_logg) fitParams.push('logg')
  if (settings.fit_monh) fitParams.push('monh')
  if (settings.fit_vmic) fitParams.push('vmic')
  if (settings.fit_vmac) fitParams.push('vmac')
  if (settings.fit_vsini) fitParams.push('vsini')

  if (fitParams.length === 0) {
    error.value = 'No parameters selected for fitting'
    return
  }

  solving.value = true
  error.value = null
  status.value = 'Starting fit...'

  try {
    await api.solve(fitParams)

    const eventSource = api.solveStream()

    eventSource.onmessage = async (event) => {
      const data = JSON.parse(event.data)

      if (data.type === 'progress') {
        status.value = `Fitting... iteration ${data.iteration}`
      } else if (data.type === 'done') {
        eventSource.close()
        solving.value = false
        await refreshSession()
        plotKey.value++
        status.value = `Fit complete (chi-sq: ${data.chisq?.toFixed(3) || 'N/A'})`
      } else if (data.type === 'error') {
        eventSource.close()
        solving.value = false
        error.value = data.message
        status.value = null
      } else if (data.type === 'cancelled') {
        eventSource.close()
        solving.value = false
        status.value = 'Fit cancelled'
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
      solving.value = false
      error.value = 'Connection to server lost'
      status.value = null
    }
  } catch (e) {
    solving.value = false
    error.value = e instanceof Error ? e.message : 'Solve failed'
    status.value = null
  }
}

async function handleCancel() {
  try {
    await api.cancelSolve()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to cancel'
  }
}

async function handleMCMC() {
  if (!session.value) return

  const fitParams: string[] = []
  const settings = session.value.fit_settings
  if (settings.fit_teff) fitParams.push('teff')
  if (settings.fit_logg) fitParams.push('logg')
  if (settings.fit_monh) fitParams.push('monh')
  if (settings.fit_vmic) fitParams.push('vmic')
  if (settings.fit_vmac) fitParams.push('vmac')
  if (settings.fit_vsini) fitParams.push('vsini')

  if (fitParams.length === 0 && session.value.fit_abundances.length === 0) {
    error.value = 'No parameters selected for MCMC'
    return
  }

  runningMCMC.value = true
  error.value = null
  status.value = 'Starting MCMC...'

  try {
    await api.runMCMC(fitParams)

    const eventSource = api.mcmcStream()

    eventSource.onmessage = async (event) => {
      const data = JSON.parse(event.data)

      if (data.type === 'progress') {
        status.value = `MCMC... step ${data.iteration}`
      } else if (data.type === 'done') {
        eventSource.close()
        runningMCMC.value = false
        await refreshSession()
        plotKey.value++
        const acc = data.acceptance_fraction ? (data.acceptance_fraction * 100).toFixed(1) : 'N/A'
        status.value = `MCMC complete (acceptance: ${acc}%)`
      } else if (data.type === 'error') {
        eventSource.close()
        runningMCMC.value = false
        error.value = data.message
        status.value = null
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
      runningMCMC.value = false
      error.value = 'Connection to server lost'
      status.value = null
    }
  } catch (e) {
    runningMCMC.value = false
    error.value = e instanceof Error ? e.message : 'MCMC failed'
    status.value = null
  }
}

onMounted(async () => {
  await refreshSession()
})
</script>

<template>
  <div class="app">
    <header class="header">
      <div class="header-content">
        <h1>PySME</h1>
        <span class="subtitle">Spectroscopy Made Easy</span>
      </div>
      <nav class="header-nav">
        <a href="https://pysme-astro.readthedocs.io/" target="_blank">Documentation</a>
        <a href="https://github.com/MingjieJian/SME" target="_blank">GitHub</a>
      </nav>
    </header>

    <main class="main">
      <div v-if="error" class="message error">{{ error }}</div>
      <div v-if="status" class="message status">{{ status }}</div>

      <section class="section file-section">
        <FileControls
          :loading="loading"
          :filename="session?.filename"
          @new-session="handleNewSession"
          @file-loaded="handleFileLoaded"
          @error="error = $event"
        />
      </section>

      <section v-if="hasData" class="section plot-section">
        <SpectrumPlot :key="plotKey" />
      </section>

      <section v-if="session" class="section params-section">
        <ParameterForm
          :params="session.stellar_params"
          :fit-settings="session.fit_settings"
          :instrument="session.instrument"
          :continuum="session.continuum"
          :radial-velocity="session.radial_velocity"
          :has-linelist="session.has_linelist"
          :wave-range="waveRange"
          :abund-pattern="session.abund_pattern"
          :nlte-enabled="session.nlte_enabled"
          :forward-mode="forwardMode"
          :fit-abundances="session.fit_abundances"
          :available-elements="session.available_elements"
          @update-params="handleParamsChanged"
          @update-fit-settings="handleFitSettingsChanged"
          @update-instrument="handleInstrumentChanged"
          @update-continuum="handleContinuumChanged"
          @update-abund-pattern="handleAbundPatternChanged"
          @update-wave-limits="handleWaveLimitsChanged"
          @update-wave-limits-multi="handleWaveLimitsMultiChanged"
          @update-nlte="handleNlteChanged"
          @update-fit-abundances="handleFitAbundancesChanged"
          @linelist-loaded="refreshSession"
          @error="error = $event"
        />
      </section>

      <section v-if="session" class="section actions-section">
        <div class="actions">
          <label class="mode-toggle">
            <input type="checkbox" v-model="forwardMode" />
            Forward modeling only
          </label>
          <button
            class="btn primary"
            :disabled="!canSynthesize || synthesizing || solving"
            @click="handleSynthesize"
          >
            {{ synthesizing ? 'Synthesizing...' : 'Synthesize' }}
          </button>
          <button
            v-if="!forwardMode"
            class="btn primary"
            :disabled="!canSolve || synthesizing || solving || runningMCMC"
            @click="handleSolve"
          >
            {{ solving ? 'Solving...' : 'Solve' }}
          </button>
          <button
            v-if="!forwardMode"
            class="btn secondary"
            :disabled="!canSolve || synthesizing || solving || runningMCMC"
            @click="handleMCMC"
            title="Run MCMC parameter estimation for Bayesian uncertainties"
          >
            {{ runningMCMC ? 'MCMC...' : 'MCMC' }}
          </button>
          <button
            v-if="solving || runningMCMC"
            class="btn danger"
            @click="handleCancel"
          >
            Cancel
          </button>
        </div>
      </section>

      <section v-if="fitResults || mcmcResults" class="section results-section">
        <FitResults :results="fitResults" :mcmc-results="mcmcResults" />
      </section>
    </main>

    <footer class="footer">
      <p>PySME Web GUI v0.5.0</p>
    </footer>
  </div>
</template>

<style>
:root {
  --primary: #2563eb;
  --primary-dark: #1d4ed8;
  --danger: #dc2626;
  --success: #16a34a;
  --bg: #f8fafc;
  --bg-card: #ffffff;
  --text: #1e293b;
  --text-muted: #64748b;
  --border: #e2e8f0;
  --header-bg: #1e3a5f;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
}

.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.header {
  background: var(--header-bg);
  color: white;
  padding: 1rem 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-content {
  display: flex;
  align-items: baseline;
  gap: 1rem;
}

.header h1 {
  font-size: 1.5rem;
  font-weight: 700;
}

.subtitle {
  opacity: 0.8;
  font-size: 0.9rem;
}

.header-nav {
  display: flex;
  gap: 1.5rem;
}

.header-nav a {
  color: white;
  text-decoration: none;
  opacity: 0.9;
}

.header-nav a:hover {
  opacity: 1;
  text-decoration: underline;
}

.main {
  flex: 1;
  padding: 1.5rem 2rem;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

.section {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.message {
  padding: 0.75rem 1rem;
  border-radius: 6px;
  margin-bottom: 1rem;
}

.message.error {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.message.status {
  background: #f0fdf4;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.actions {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

.btn {
  padding: 0.625rem 1.25rem;
  border-radius: 6px;
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: background-color 0.15s;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn.primary {
  background: var(--primary);
  color: white;
}

.btn.primary:hover:not(:disabled) {
  background: var(--primary-dark);
}

.btn.secondary {
  background: #6b7280;
  color: white;
}

.btn.secondary:hover:not(:disabled) {
  background: #4b5563;
}

.btn.danger {
  background: var(--danger);
  color: white;
}

.btn.danger:hover:not(:disabled) {
  background: #b91c1c;
}

.mode-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  cursor: pointer;
  margin-right: 1rem;
}

.mode-toggle input {
  width: 16px;
  height: 16px;
}

.footer {
  background: var(--bg-card);
  border-top: 1px solid var(--border);
  padding: 1rem 2rem;
  text-align: center;
  color: var(--text-muted);
  font-size: 0.875rem;
}
</style>

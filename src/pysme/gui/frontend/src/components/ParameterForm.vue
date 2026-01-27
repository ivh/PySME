<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { api } from '../api'
import type { StellarParams, FitSettings, InstrumentSettings, ContinuumSettings, RadialVelocitySettings } from '../api'

const props = defineProps<{
  params: StellarParams
  fitSettings: FitSettings
  instrument: InstrumentSettings
  continuum: ContinuumSettings
  radialVelocity: RadialVelocitySettings
  hasLinelist: boolean
  waveRange: [number, number] | null
  abundPattern: string
}>()

const emit = defineEmits<{
  'update-params': [params: Partial<StellarParams>]
  'update-fit-settings': [settings: FitSettings]
  'update-instrument': [settings: Partial<InstrumentSettings>]
  'update-continuum': [settings: Partial<ContinuumSettings>]
  'update-vrad': [settings: Partial<RadialVelocitySettings>]
  'update-abund-pattern': [pattern: string]
  'update-wave-limits': [limits: { wl_min: number; wl_max: number }]
  'linelist-loaded': []
  'error': [message: string]
}>()

const localParams = ref<StellarParams>({ ...props.params })
const localFitSettings = ref<FitSettings>({ ...props.fitSettings })
const localInstrument = ref({
  ipres: props.instrument.ipres ?? 100000,
  iptype: props.instrument.iptype || 'gauss',
  snr: 100,
  vrad: 0,
})
const localContinuum = ref<ContinuumSettings>({ ...props.continuum })
const localAbundPattern = ref(props.abundPattern || 'asplund2021')
const localWlMin = ref<number | null>(null)
const localWlMax = ref<number | null>(null)
const doNlte = ref(false)
const retainContinuum = ref(false)

const linelistFileInput = ref<HTMLInputElement | null>(null)
const selectedLinelist = ref('user')

watch(() => props.params, (newParams) => {
  localParams.value = { ...newParams }
}, { deep: true })

watch(() => props.fitSettings, (newSettings) => {
  localFitSettings.value = { ...newSettings }
}, { deep: true })

watch(() => props.instrument, (newSettings) => {
  localInstrument.value.ipres = newSettings.ipres ?? 100000
  localInstrument.value.iptype = newSettings.iptype || 'gauss'
}, { deep: true })

watch(() => props.continuum, (newSettings) => {
  localContinuum.value = { ...newSettings }
  retainContinuum.value = newSettings.cscale_flag === 'none'
}, { deep: true })

watch(() => props.waveRange, (range) => {
  if (range && localWlMin.value === null) {
    localWlMin.value = range[0]
    localWlMax.value = range[1]
  }
})

watch(() => props.abundPattern, (pattern) => {
  localAbundPattern.value = pattern || 'asplund2021'
})

function updateParam(key: keyof StellarParams, value: number | null) {
  localParams.value[key] = value
  emit('update-params', { [key]: value })
}

function updateFitSetting(key: keyof FitSettings, value: boolean) {
  localFitSettings.value[key] = value
  emit('update-fit-settings', localFitSettings.value)
}

async function updateInstrument() {
  emit('update-instrument', {
    ipres: localInstrument.value.ipres,
    iptype: localInstrument.value.iptype,
  })
}

function updateAbundPattern(pattern: string) {
  localAbundPattern.value = pattern
  emit('update-abund-pattern', pattern)
}

function updateWaveLimits() {
  if (localWlMin.value !== null && localWlMax.value !== null) {
    emit('update-wave-limits', {
      wl_min: localWlMin.value,
      wl_max: localWlMax.value,
    })
  }
}

function updateContinuumRetain() {
  const flag = retainContinuum.value ? 'none' : 'linear'
  emit('update-continuum', { cscale_flag: flag })
}

async function handleLinelistFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  try {
    await api.loadLinelist(file)
    selectedLinelist.value = 'user'
    emit('linelist-loaded')
  } catch (e) {
    emit('error', e instanceof Error ? e.message : 'Failed to load linelist')
  } finally {
    input.value = ''
  }
}

const stellarParamDefs = [
  { key: 'teff', label: 'Teff', unit: 'K', fitKey: 'fit_teff', step: 50, default: 5800 },
  { key: 'logg', label: 'logg', unit: 'dex', fitKey: 'fit_logg', step: 0.1, default: 4.4 },
  { key: 'monh', label: 'monh', unit: 'dex', fitKey: 'fit_monh', step: 0.1, default: 0.0 },
  { key: 'vmic', label: 'Vmic', unit: 'km/s', fitKey: 'fit_vmic', step: 0.1, default: 1.0 },
  { key: 'vmac', label: 'Vmac', unit: 'km/s', fitKey: 'fit_vmac', step: 0.5, default: 1.0 },
  { key: 'vsini', label: 'Vsini', unit: 'km/s', fitKey: 'fit_vsini', step: 1, default: 1.0 },
] as const

const abundanceOptions = [
  { value: 'asplund2021', label: 'Asplund 2021' },
  { value: 'asplund2009', label: 'Asplund 2009' },
  { value: 'grevesse2007', label: 'Grevesse 2007' },
  { value: 'lodders2003', label: 'Lodders 2003' },
]

const linelistOptions = [
  { value: 'user', label: 'User linelist (VALD)', isUpload: true },
]
</script>

<template>
  <div class="parameter-form">
    <div class="form-grid">
      <!-- Instr. specs & Source -->
      <div class="form-column">
        <h3>Instr. specs & Source</h3>
        <div class="param-list">
          <div class="param-row">
            <label class="param-label" title="Instrumental resolution (ipres): wavelength/delta-wavelength">
              Instrumental broadening
            </label>
            <div class="param-input">
              <input
                type="number"
                v-model.number="localInstrument.ipres"
                @change="updateInstrument"
                step="1000"
                min="0"
              />
            </div>
          </div>
          <div class="param-row">
            <label class="param-label" title="Typical signal-to-noise ratio of provided spectrum">
              SNR
            </label>
            <div class="param-input">
              <input
                type="number"
                v-model.number="localInstrument.snr"
                step="10"
                min="1"
              />
            </div>
          </div>
          <div class="param-row">
            <label class="param-label" title="Radial velocity in km/s">
              Vrad
            </label>
            <div class="param-input">
              <input
                type="number"
                v-model.number="localInstrument.vrad"
                step="1"
              />
              <span class="unit">km/s</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Stellar Parameters -->
      <div class="form-column">
        <h3>Stellar parameters</h3>
        <div class="param-list">
          <div v-for="param in stellarParamDefs" :key="param.key" class="param-row">
            <label class="param-label">
              <input
                type="checkbox"
                :checked="localFitSettings[param.fitKey]"
                @change="updateFitSetting(param.fitKey, ($event.target as HTMLInputElement).checked)"
                title="Check to fit this parameter"
              />
              {{ param.label }}
            </label>
            <div class="param-input">
              <input
                type="number"
                :value="localParams[param.key] ?? param.default"
                :step="param.step"
                @change="updateParam(param.key, parseFloat(($event.target as HTMLInputElement).value) || null)"
              />
              <span class="unit">{{ param.unit }}</span>
            </div>
          </div>
        </div>
        <p class="info">
          Checked: Parameter will be derived by SME using initial guess from textbox.<br>
          Unchecked: Parameter is fixed to the textbox value.
        </p>
      </div>

      <!-- References -->
      <div class="form-column">
        <h3>Solar ref. composition</h3>
        <div class="radio-list">
          <label v-for="opt in abundanceOptions" :key="opt.value" class="radio-row">
            <input
              type="radio"
              name="abund"
              :value="opt.value"
              :checked="localAbundPattern === opt.value"
              @change="updateAbundPattern(opt.value)"
            />
            {{ opt.label }}
          </label>
        </div>

        <h3>Linelist</h3>
        <div class="radio-list">
          <label class="radio-row upload-row">
            <input
              type="radio"
              name="linelist"
              value="user"
              :checked="selectedLinelist === 'user'"
              @change="selectedLinelist = 'user'"
            />
            <a href="#" @click.prevent="linelistFileInput?.click()">User linelist (VALD)</a>
            <input
              ref="linelistFileInput"
              type="file"
              accept=".lin,.vald,.txt"
              style="display: none"
              @change="handleLinelistFileSelect"
            />
          </label>
        </div>
        <div class="status-item" :class="{ active: hasLinelist }">
          <span class="status-icon">{{ hasLinelist ? 'OK' : '--' }}</span>
          Linelist loaded
        </div>
      </div>

      <!-- Options -->
      <div class="form-column">
        <h3>Wavelength limits</h3>
        <div class="wavelength-row">
          <span>From</span>
          <input
            type="number"
            v-model.number="localWlMin"
            @change="updateWaveLimits"
            step="0.1"
            class="wl-input"
          />
          <span>to</span>
          <input
            type="number"
            v-model.number="localWlMax"
            @change="updateWaveLimits"
            step="0.1"
            class="wl-input"
          />
          <span>A</span>
        </div>

        <h3>Options</h3>
        <div class="checkbox-list">
          <label class="checkbox-row">
            <input
              type="checkbox"
              v-model="doNlte"
            />
            NLTE (H, Li, C, N, O, Na, Mg, Al, Si, K, Ca, Ti, Mn, Fe, Cu, Ba)
          </label>
          <label class="checkbox-row">
            <input
              type="checkbox"
              v-model="retainContinuum"
              @change="updateContinuumRetain"
            />
            Retain continuum level of input spectrum
          </label>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.parameter-form {
  font-size: 0.9rem;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 2rem;
}

.form-column h3 {
  font-size: 0.9rem;
  font-weight: 600;
  margin-bottom: 0.75rem;
  padding: 0.5rem;
  background: var(--header-bg);
  color: white;
  border-radius: 4px;
}

.form-column h3:not(:first-child) {
  margin-top: 1.5rem;
}

.param-list,
.radio-list,
.checkbox-list {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.param-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.param-label {
  flex: 0 0 140px;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-weight: 500;
  color: var(--text);
  font-size: 0.85rem;
}

.param-label input[type="checkbox"] {
  width: 15px;
  height: 15px;
}

.param-input {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.param-input input {
  flex: 1;
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.85rem;
  background: var(--bg-card);
  max-width: 100px;
}

.param-input input:focus {
  outline: none;
  border-color: var(--primary);
}

.unit {
  font-size: 0.75rem;
  color: var(--text-muted);
  min-width: 35px;
}

.radio-row,
.checkbox-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
  cursor: pointer;
}

.radio-row input,
.checkbox-row input {
  width: 14px;
  height: 14px;
}

.upload-row a {
  color: var(--primary);
  text-decoration: none;
}

.upload-row a:hover {
  text-decoration: underline;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-muted);
  font-size: 0.85rem;
  margin-top: 0.5rem;
}

.status-item.active {
  color: var(--success);
}

.status-icon {
  font-weight: 600;
  font-size: 0.75rem;
}

.wavelength-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
}

.wl-input {
  width: 80px;
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.85rem;
}

.wl-input:focus {
  outline: none;
  border-color: var(--primary);
}

.info {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 0.75rem;
  line-height: 1.4;
}
</style>

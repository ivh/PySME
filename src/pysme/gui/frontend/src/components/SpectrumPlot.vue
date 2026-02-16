<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { api } from '../api'

const emit = defineEmits<{
  'mask-updated': []
  'set-wave-from-view': [limits: { wl_min: number; wl_max: number }]
}>()

const plotContainer = ref<HTMLDivElement | null>(null)
const segment = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
const nseg = ref(0)

const maskEditMode = ref(false)
const selectedMaskValue = ref(1)
const selectionRange = ref<{min: number, max: number} | null>(null)

const currentXRange = ref<{ min: number; max: number } | null>(null)

const maskLabels: Record<number, string> = {
  0: 'Bad',
  1: 'Line',
  2: 'Continuum'
}

async function loadPlot() {
  if (!plotContainer.value) return

  loading.value = true
  error.value = null

  try {
    const session = await api.getSession()
    nseg.value = session.nseg

    if (!session.has_observation && !session.has_synthetic) {
      Plotly.purge(plotContainer.value)
      return
    }

    const plotData = await api.getSpectrumPlot(segment.value)

    const layout = {
      ...(plotData as any).layout,
      autosize: true,
      margin: { l: 60, r: 30, t: 40, b: 50 },
      height: 400,
      dragmode: maskEditMode.value ? 'select' : 'zoom',
    }

    await Plotly.react(
      plotContainer.value,
      (plotData as any).data,
      layout,
      { responsive: true }
    )

    ;(plotContainer.value as any).on('plotly_relayout', (eventData: any) => {
      if (eventData['xaxis.range[0]'] !== undefined && eventData['xaxis.range[1]'] !== undefined) {
        currentXRange.value = {
          min: eventData['xaxis.range[0]'],
          max: eventData['xaxis.range[1]'],
        }
      } else if (eventData['xaxis.autorange']) {
        currentXRange.value = null
      }
    })

    if (maskEditMode.value) {
      setupSelectionHandler()
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load plot'
  } finally {
    loading.value = false
  }
}

function setupSelectionHandler() {
  if (!plotContainer.value) return

  (plotContainer.value as any).on('plotly_selected', async (eventData: any) => {
    if (!eventData || !eventData.range) return

    const xRange = eventData.range.x
    if (!xRange || xRange.length < 2) return

    selectionRange.value = {
      min: Math.min(xRange[0], xRange[1]),
      max: Math.max(xRange[0], xRange[1])
    }
  })
}

async function applyMask() {
  if (!selectionRange.value) return

  try {
    await api.updateMask(
      segment.value,
      selectionRange.value.min,
      selectionRange.value.max,
      selectedMaskValue.value
    )
    selectionRange.value = null
    await loadPlot()
    emit('mask-updated')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to update mask'
  }
}

function cancelSelection() {
  selectionRange.value = null
  if (plotContainer.value) {
    Plotly.relayout(plotContainer.value, { selections: [] })
  }
}

function setWaveFromView() {
  if (currentXRange.value) {
    emit('set-wave-from-view', {
      wl_min: currentXRange.value.min,
      wl_max: currentXRange.value.max,
    })
  }
}

function toggleMaskMode() {
  maskEditMode.value = !maskEditMode.value
  selectionRange.value = null
  loadPlot()
}

function changeSegment(delta: number) {
  const newSeg = segment.value + delta
  if (newSeg >= 0 && newSeg < nseg.value) {
    segment.value = newSeg
  }
}

watch(segment, () => {
  selectionRange.value = null
  loadPlot()
})

onMounted(() => {
  loadPlot()
})
</script>

<template>
  <div class="spectrum-plot">
    <div class="plot-header">
      <h2>Spectrum</h2>
      <div class="header-controls">
        <button
          v-if="currentXRange"
          type="button"
          class="btn-set-range"
          @click="setWaveFromView"
          title="Set wavelength limits from the current plot view"
        >
          Use current view ({{ currentXRange.min.toFixed(1) }}-{{ currentXRange.max.toFixed(1) }} A)
        </button>
        <button
          type="button"
          class="mask-toggle"
          :class="{ active: maskEditMode }"
          @click="toggleMaskMode"
        >
          {{ maskEditMode ? 'Exit mask edit' : 'Edit mask' }}
        </button>
        <div v-if="nseg > 1" class="segment-controls">
          <button @click="changeSegment(-1)" :disabled="segment <= 0">Prev</button>
          <span>Segment {{ segment + 1 }} / {{ nseg }}</span>
          <button @click="changeSegment(1)" :disabled="segment >= nseg - 1">Next</button>
        </div>
      </div>
    </div>

    <div v-if="maskEditMode" class="mask-controls">
      <span class="mask-instruction">Select a region on the plot, then set mask value:</span>
      <select v-model.number="selectedMaskValue" class="mask-select">
        <option :value="0">Bad (0)</option>
        <option :value="1">Line (1)</option>
        <option :value="2">Continuum (2)</option>
      </select>
      <template v-if="selectionRange">
        <span class="selection-info">
          Selected: {{ selectionRange.min.toFixed(2) }} - {{ selectionRange.max.toFixed(2) }} A
        </span>
        <button type="button" class="btn-apply" @click="applyMask">Apply</button>
        <button type="button" class="btn-cancel" @click="cancelSelection">Cancel</button>
      </template>
    </div>

    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="loading" class="loading">Loading plot...</div>

    <div ref="plotContainer" class="plot-container"></div>
  </div>
</template>

<style scoped>
.spectrum-plot {
  width: 100%;
}

.plot-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.plot-header h2 {
  font-size: 1.1rem;
  color: var(--text);
  margin: 0;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.btn-set-range {
  padding: 0.3rem 0.75rem;
  border: 1px solid var(--primary);
  border-radius: 4px;
  background: var(--bg-card);
  color: var(--primary);
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
}

.btn-set-range:hover {
  background: #f0f7ff;
}

.mask-toggle {
  padding: 0.3rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-card);
  cursor: pointer;
  font-size: 0.85rem;
}

.mask-toggle:hover {
  background: var(--bg);
}

.mask-toggle.active {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.segment-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.segment-controls button {
  padding: 0.3rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-card);
  cursor: pointer;
  font-size: 0.85rem;
}

.segment-controls button:hover:not(:disabled) {
  background: var(--bg);
}

.segment-controls button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.segment-controls span {
  font-size: 0.9rem;
  color: var(--text-muted);
}

.mask-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  background: #f0f7ff;
  border: 1px solid #bfdbfe;
  border-radius: 4px;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}

.mask-instruction {
  font-size: 0.85rem;
  color: var(--text);
}

.mask-select {
  padding: 0.3rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.85rem;
}

.selection-info {
  font-size: 0.85rem;
  color: var(--primary);
  font-weight: 500;
}

.btn-apply {
  padding: 0.3rem 0.75rem;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
}

.btn-apply:hover {
  background: var(--primary-dark);
}

.btn-cancel {
  padding: 0.3rem 0.75rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
}

.btn-cancel:hover {
  background: var(--bg);
}

.plot-container {
  width: 100%;
  min-height: 400px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: white;
}

.error {
  color: var(--danger);
  padding: 0.5rem;
  font-size: 0.9rem;
}

.loading {
  color: var(--text-muted);
  padding: 0.5rem;
  font-size: 0.9rem;
}
</style>

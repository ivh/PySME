<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { api } from '../api'

const plotContainer = ref<HTMLDivElement | null>(null)
const segment = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
const nseg = ref(0)

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

    await Plotly.react(
      plotContainer.value,
      (plotData as any).data,
      {
        ...(plotData as any).layout,
        autosize: true,
        margin: { l: 60, r: 30, t: 40, b: 50 },
        height: 400,
      },
      { responsive: true }
    )
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load plot'
  } finally {
    loading.value = false
  }
}

function changeSegment(delta: number) {
  const newSeg = segment.value + delta
  if (newSeg >= 0 && newSeg < nseg.value) {
    segment.value = newSeg
  }
}

watch(segment, () => {
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
      <div v-if="nseg > 1" class="segment-controls">
        <button @click="changeSegment(-1)" :disabled="segment <= 0">Prev</button>
        <span>Segment {{ segment + 1 }} / {{ nseg }}</span>
        <button @click="changeSegment(1)" :disabled="segment >= nseg - 1">Next</button>
      </div>
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

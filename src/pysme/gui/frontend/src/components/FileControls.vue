<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api'

defineProps<{
  loading: boolean
  filename: string | null
}>()

const emit = defineEmits<{
  'new-session': []
  'file-loaded': []
  'error': [message: string]
}>()

const smeFileInput = ref<HTMLInputElement | null>(null)
const spectrumFileInput = ref<HTMLInputElement | null>(null)
const linelistFileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)

async function handleSmeFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  uploading.value = true
  try {
    await api.loadSession(file)
    emit('file-loaded')
  } catch (e) {
    emit('error', e instanceof Error ? e.message : 'Failed to load file')
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function handleSpectrumFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  uploading.value = true
  try {
    await api.loadSpectrum(file)
    emit('file-loaded')
  } catch (e) {
    emit('error', e instanceof Error ? e.message : 'Failed to load spectrum')
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function handleLinelistFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  uploading.value = true
  try {
    await api.loadLinelist(file)
    emit('file-loaded')
  } catch (e) {
    emit('error', e instanceof Error ? e.message : 'Failed to load linelist')
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function handleLoadTest() {
  uploading.value = true
  try {
    await api.loadTestSpectrum()
    emit('file-loaded')
  } catch (e) {
    emit('error', e instanceof Error ? e.message : 'Failed to load test spectrum')
  } finally {
    uploading.value = false
  }
}

async function handleLoadSolar() {
  uploading.value = true
  try {
    await api.loadSolarSpectrum()
    emit('file-loaded')
  } catch (e) {
    emit('error', e instanceof Error ? e.message : 'Failed to load solar spectrum')
  } finally {
    uploading.value = false
  }
}

async function handleSave() {
  try {
    const blob = await api.saveSession()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'spectrum.sme'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    emit('error', e instanceof Error ? e.message : 'Failed to save file')
  }
}
</script>

<template>
  <div class="file-controls">
    <h2>File</h2>
    <div class="buttons">
      <button class="btn" @click="$emit('new-session')" :disabled="loading || uploading">
        New Session
      </button>

      <input
        ref="smeFileInput"
        type="file"
        accept=".sme,.npy,.npz,.sav,.inp,.out,.ech"
        style="display: none"
        @change="handleSmeFileSelect"
      />
      <button
        class="btn primary"
        @click="smeFileInput?.click()"
        :disabled="loading || uploading"
      >
        Load .sme File
      </button>

      <input
        ref="spectrumFileInput"
        type="file"
        accept=".fits,.csv"
        style="display: none"
        @change="handleSpectrumFileSelect"
      />
      <button
        class="btn"
        @click="spectrumFileInput?.click()"
        :disabled="loading || uploading"
      >
        Load Spectrum (FITS/CSV)
      </button>

      <input
        ref="linelistFileInput"
        type="file"
        accept=".lin,.vald"
        style="display: none"
        @change="handleLinelistFileSelect"
      />
      <button
        class="btn"
        @click="linelistFileInput?.click()"
        :disabled="loading || uploading"
      >
        Load Linelist (VALD)
      </button>

      <button class="btn" @click="handleLoadTest" :disabled="loading || uploading">
        Load Test Spectrum
      </button>

      <button class="btn" @click="handleLoadSolar" :disabled="loading || uploading">
        Load Solar Spectrum
      </button>

      <button class="btn" @click="handleSave" :disabled="loading || uploading">
        Save .sme
      </button>
    </div>

    <div v-if="filename" class="filename">
      Current file: <strong>{{ filename }}</strong>
    </div>
  </div>
</template>

<style scoped>
.file-controls h2 {
  margin-bottom: 1rem;
  font-size: 1.1rem;
  color: var(--text);
}

.buttons {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.btn {
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text);
  transition: all 0.15s;
}

.btn:hover:not(:disabled) {
  background: var(--bg);
  border-color: var(--text-muted);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn.primary {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.btn.primary:hover:not(:disabled) {
  background: var(--primary-dark);
}

.filename {
  margin-top: 1rem;
  font-size: 0.9rem;
  color: var(--text-muted);
}
</style>

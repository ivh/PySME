<script setup lang="ts">
import type { FitResult } from '../api'

defineProps<{
  results: FitResult
}>()

const paramLabels: Record<string, string> = {
  teff: 'Teff (K)',
  logg: 'log g',
  monh: '[M/H]',
  vmic: 'Vmic (km/s)',
  vmac: 'Vmac (km/s)',
  vsini: 'Vsini (km/s)',
}

function formatValue(value: number, param: string): string {
  if (param === 'teff') {
    return value.toFixed(0)
  }
  return value.toFixed(3)
}

function formatUncertainty(unc: number, param: string): string {
  if (param === 'teff') {
    return unc.toFixed(0)
  }
  return unc.toFixed(3)
}
</script>

<template>
  <div class="fit-results">
    <h2>Fit Results</h2>

    <div class="summary">
      <div class="stat">
        <span class="label">Reduced Chi-squared:</span>
        <span class="value">{{ results.chisq.toFixed(4) }}</span>
      </div>
      <div class="stat">
        <span class="label">Iterations:</span>
        <span class="value">{{ results.iterations }}</span>
      </div>
    </div>

    <table class="results-table">
      <thead>
        <tr>
          <th>Parameter</th>
          <th>Value</th>
          <th>Uncertainty</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(param, index) in results.parameters" :key="param">
          <td>{{ paramLabels[param] || param }}</td>
          <td class="value">{{ formatValue(results.values[index], param) }}</td>
          <td class="uncertainty">+/- {{ formatUncertainty(results.uncertainties[index], param) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.fit-results h2 {
  font-size: 1.1rem;
  margin-bottom: 1rem;
  color: var(--text);
}

.summary {
  display: flex;
  gap: 2rem;
  margin-bottom: 1.5rem;
  padding: 1rem;
  background: var(--bg);
  border-radius: 6px;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.stat .label {
  font-size: 0.85rem;
  color: var(--text-muted);
}

.stat .value {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text);
}

.results-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.results-table th,
.results-table td {
  padding: 0.6rem 1rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.results-table th {
  font-weight: 600;
  color: var(--text-muted);
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.results-table td.value {
  font-weight: 600;
  font-family: monospace;
}

.results-table td.uncertainty {
  color: var(--text-muted);
  font-family: monospace;
}
</style>

<script setup lang="ts">
import type { FitResult, MCMCResult } from '../api'

const props = defineProps<{
  results: FitResult | null
  mcmcResults: MCMCResult | null
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

function formatAsymmetricUnc(lo: number, hi: number, param: string): string {
  const fmt = param === 'teff' ? 0 : 3
  return `-${lo.toFixed(fmt)} / +${hi.toFixed(fmt)}`
}

function getParamLabel(param: string): string {
  if (param.startsWith('abund ')) {
    return `[${param.split(' ')[1]}/H]`
  }
  return paramLabels[param] || param
}
</script>

<template>
  <div class="fit-results">
    <!-- Least-squares results -->
    <template v-if="results">
      <h2>Fit Results (Least-Squares)</h2>

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
            <td>{{ getParamLabel(param) }}</td>
            <td class="value">{{ formatValue(results.values[index], param) }}</td>
            <td class="uncertainty">+/- {{ formatUncertainty(results.uncertainties[index], param) }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- MCMC results -->
    <template v-if="mcmcResults">
      <h2>MCMC Results</h2>

      <div class="summary">
        <div class="stat">
          <span class="label">Acceptance Fraction:</span>
          <span class="value">{{ (mcmcResults.acceptance_fraction * 100).toFixed(1) }}%</span>
        </div>
      </div>

      <table class="results-table">
        <thead>
          <tr>
            <th>Parameter</th>
            <th>Median</th>
            <th>Uncertainty (16%-84%)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(param, index) in mcmcResults.parameters" :key="param">
            <td>{{ getParamLabel(param) }}</td>
            <td class="value">{{ formatValue(mcmcResults.values[index], param) }}</td>
            <td class="uncertainty mcmc">
              {{ formatAsymmetricUnc(mcmcResults.uncertainties_low[index], mcmcResults.uncertainties_high[index], param) }}
            </td>
          </tr>
        </tbody>
      </table>
    </template>

    <div v-if="!results && !mcmcResults" class="no-results">
      No fit results yet. Run Solve or MCMC to fit parameters.
    </div>
  </div>
</template>

<style scoped>
.fit-results h2 {
  font-size: 1.1rem;
  margin-bottom: 1rem;
  color: var(--text);
}

.fit-results h2:not(:first-child) {
  margin-top: 2rem;
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

.results-table td.uncertainty.mcmc {
  color: var(--primary);
}

.no-results {
  color: var(--text-muted);
  font-size: 0.9rem;
  padding: 1rem;
  text-align: center;
}
</style>

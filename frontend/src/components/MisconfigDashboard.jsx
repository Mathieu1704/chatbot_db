// src/components/MisconfigDashboard.jsx
import React from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip as ReTooltip, CartesianGrid,
  PieChart, Pie, Cell, ResponsiveContainer
} from 'recharts'

/* ── palette centralisée ───────────────────────────────────────── */
const palette = {
  healthy: '#10B981',
  ko:      '#EF4444',
  warning: '#FBBF24',
  bar:     '#3B82F6',
  kpi1:    '#7C3AED',
  kpi2:    '#93C5FD',
  kpi3:    '#3B82F6',
}

/* ── KPI coloré ───────────────────────────────────────────────── */
function Kpi({ title, value, color }) {
  return (
    <div
      className="p-4 rounded-xl shadow flex flex-col overflow-hidden min-w-0"
      style={{ background: color }}
    >
      <span className="text-sm text-white/80">{title}</span>
      <span className="text-2xl font-bold text-white">{value}</span>
    </div>
  )
}

/* ── légende partagée pour tous les charts ───────────────────────── */
function ChartLegend({ items }) {
  return (
    <div className="mt-3 flex flex-wrap justify-center gap-4 text-sm">
      {items.map((d, i) => (
        <div key={i} className="flex items-center space-x-1">
          <span
            className="inline-block w-3 h-3 rounded-sm flex-shrink-0"
            style={{ background: d.color }}
          />
          <span className="truncate">{d.name}</span>
          <span className="font-medium">{d.value}</span>
          <span className="text-gray-500">({d.pct})</span>
        </div>
      ))}
    </div>
  )
}

/* ── dashboard principal ───────────────────────────────────────── */
export default function MisconfigDashboard({ data }) {
  if (!data?.counts) return null

  const { counts, bySeverity } = data
  const totalAssets = counts.healthy + counts.misconfigured
  const pctKO = counts.total_assets
    ? ((counts.misconfigured * 100) / counts.total_assets).toFixed(1) + ' %'
    : '0 %'

  /* Donut data + légende */
  const donutData = [
    { name: 'Sains', value: counts.healthy,       color: palette.healthy },
    { name: 'KO',    value: counts.misconfigured, color: palette.ko },
  ]
  const legendDonut = donutData.map(d => ({
    ...d,
    pct: totalAssets ? (d.value * 100 / totalAssets).toFixed(1) + ' %' : '0 %'
  }))

  /* Légende pour le BarChart “Par Sévérité” */
  const legendSev = bySeverity.map(entry => {
    const color =
      entry._id === 'Critical' ? palette.ko
      : entry._id === 'Warning'  ? palette.warning
                                 : palette.bar
    return {
      name:  entry._id || 'Unknown',
      value: entry.count,
      color,
      pct:   counts.misconfigured
        ? (entry.count * 100 / counts.misconfigured).toFixed(1) + ' %'
        : '0 %'
    }
  })

  return (
    <div className="grid gap-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Kpi title="Total MP" value={counts.total_assets} color={palette.kpi1} />
        <Kpi title="MP KO"    value={counts.misconfigured}  color={palette.kpi2} />
        <Kpi title="% KO"     value={pctKO}                 color={palette.kpi3} />
      </div>

      {/* ligne de graphes */}
      <div className="grid md:grid-cols-3 gap-6">
        {/* Donut Healthy vs KO */}
        <div className="bg-white rounded-xl border-2 border-gray-200 shadow-lg p-4 flex flex-col">
          <h3 className="text-sm font-medium mb-4">Healthy vs KO</h3>
          <div className="w-full h-60">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={donutData}
                  dataKey="value"
                  innerRadius="60%"
                  outerRadius="80%"
                  startAngle={90}
                  endAngle={-270}
                  stroke="none"
                  paddingAngle={3}
                >
                  {donutData.map((d, i) => (
                    <Cell key={i} fill={d.color} />
                  ))}
                </Pie>
                <ReTooltip formatter={v => [`${v} MP`, '']} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ChartLegend items={legendDonut} />
        </div>

        {/* Bar « Par Sévérité » */}
        <div className="bg-white rounded-xl border-2 border-gray-200 shadow-lg p-4 flex flex-col">
          <h3 className="text-sm font-medium mb-4">Par Sévérité</h3>
          <div className="w-full h-60">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={bySeverity}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="_id" />
                <YAxis />
                <ReTooltip
                  formatter={v => [`${v} MP`, 'count']}
                  cursor={{ fill: 'rgba(0,0,0,0.04)' }}
                />
                <Bar dataKey="count">
                  {bySeverity.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={
                        entry._id === 'Critical' ? palette.ko
                        : entry._id === 'Warning'  ? palette.warning
                                                   : palette.bar
                      }
                      radius={[4, 4, 0, 0]}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <ChartLegend items={legendSev} />
        </div>

        {/* (éventuel 3ᵉ chart) */}
      </div>
    </div>
  )
}

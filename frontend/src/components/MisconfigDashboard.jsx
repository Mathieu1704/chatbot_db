import React from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip as ReTooltip, CartesianGrid,
  LineChart, Line, PieChart, Pie, Cell, ResponsiveContainer
} from 'recharts'

/* ── palette centralisée ─────────────────────────────── */
const palette = {
  healthy:  '#10B981',
  ko:       '#EF4444',
  bar:      '#3B82F6',

  kpi1:     '#7C3AED',
  kpi2:     '#93C5FD',
  kpi3:     '#3B82F6',
}

/* ── KPI coloré ──────────────────────────────────────── */
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

/* ── dashboard principal ─────────────────────────────── */
export default function MisconfigDashboard({ data }) {
  if (!data?.counts) return null

  const { counts, byTransmitter, bySeverity, dailyNew } = data
  const pctKO = counts.total_assets
    ? ((counts.misconfigured * 100) / counts.total_assets).toFixed(1) + ' %'
    : '0 %'

  // Top 10 transmitters fautifs
  const topTx = [...byTransmitter]
    .sort((a, b) => b.faultyMP - a.faultyMP)
    .slice(0, 10)

  // Donut data + légende
  const donutData = [
    { name: 'Sains', value: counts.healthy, color: palette.healthy },
    { name: 'KO',    value: counts.misconfigured, color: palette.ko },
  ]
  const total = counts.healthy + counts.misconfigured
  const legend = donutData.map(d => ({
    ...d,
    pct: total ? (d.value * 100 / total).toFixed(1) + ' %' : '0 %'
  }))

  return (
    <div className="grid gap-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Kpi title="Total MP" value={counts.total_assets}        color={palette.kpi1} />
        <Kpi title="MP KO"    value={counts.misconfigured}       color={palette.kpi2} />
        <Kpi title="% KO"     value={pctKO}                      color={palette.kpi3} />
      </div>

      {/* ligne de graphes */}
      <div className="grid md:grid-cols-3 gap-6">
        {/* Donut Healthy vs KO */}
        <div className="bg-white rounded-xl shadow p-4">
          <h3 className="text-sm font-medium mb-4">Healthy vs KO</h3>
          <ResponsiveContainer width={240} height={240}>
            <PieChart>
              <Pie
                data={donutData}
                dataKey="value"
                innerRadius="60%"
                outerRadius="90%"
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
          <div className="mt-3 grid grid-cols-2 gap-x-4 text-sm">
            {legend.map((d, i) => (
              <div key={i} className="flex items-center space-x-2">
                <span
                  className="inline-block w-3 h-3 rounded-sm"
                  style={{ background: d.color }}
                />
                <span>{d.name}</span>
                <span className="font-medium">{d.value}</span>
                <span className="text-gray-500">({d.pct})</span>
              </div>
            ))}
          </div>
        </div>

        {/* Top 10 transmitters KO
        <div className="bg-white rounded-xl shadow p-4">
          <h3 className="text-sm font-medium mb-2">Top 10 Transmitters KO</h3>
          <BarChart
            width={350} height={240} data={topTx}
            margin={{ top: 20, right: 20, bottom: 60, left: 20 }}
          >
            <CartesianGrid strokeDasharray="3 3"/>
            <XAxis
              dataKey="transmitter" interval={0}
              tick={{ fontSize:10 }} angle={-45}
              textAnchor="end" height={60}
            />
            <YAxis />
            <ReTooltip formatter={v => [`${v} MP`, 'faultyMP']} cursor={{ fill:'rgba(0,0,0,0.04)' }}/>
            <Bar dataKey="faultyMP" fill={palette.ko} radius={[4,4,0,0]}/>
          </BarChart>
        </div> */}

        {/* Par Sévérité */}
        <div className="bg-white rounded-xl shadow p-4">
          <h3 className="text-sm font-medium mb-2">Par Sévérité</h3>
          <BarChart width={350} height={240} data={bySeverity}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="_id" />
            <YAxis />
            <ReTooltip formatter={v => [`${v} MP`, 'count']} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
            <Bar dataKey="count">
              {bySeverity.map((entry, i) => (
                <Cell
                  key={i}
                  fill={
                    entry._id === 'Critical' ? palette.ko
                    : entry._id === 'Warning'  ? palette.bar
                                               : palette.bar
                  }
                  radius={[4,4,0,0]}
                />
              ))}
            </Bar>
          </BarChart>
        </div>
      </div>

      {/* Timeline (optionnel) */}
      {false && (
        <div className="bg-white rounded-xl shadow p-4">
          <h3 className="text-sm font-medium mb-2">
            Évolution quotidienne des nouvelles misconfigs
          </h3>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={dailyNew}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="_id" />
              <YAxis />
              <ReTooltip formatter={v => [`${v} MP`, 'count']} />
              <Line type="monotone" dataKey="count" stroke={palette.bar} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

import React from 'react'
import Card from './Card'
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  RadialBarChart,
  RadialBar,
} from 'recharts'

export default function Dashboard() {
  // Données summary avec couleur hex
  const summaryItems = [
    { label: 'Assets monitored', value: 879, color: '#7C3AED' },
    { label: '% PDM Coverage',   value: '60%',                       color: '#93C5FD' },
    { label: 'Savings',           value: `$ ${Number(1045899).toLocaleString()}`, color: '#3B82F6' },
    { label: 'Risks',             value: 15,                         color: '#FBBF24' },
    { label: '% OEE Global',      value: '82%',                      color: '#10B981' },
  ]

  // Données status
  const statusData = [
    { name: 'Action required', value: 1,  color: '#EF4444' },
    { name: 'Early fault',     value: 10, color: '#FBBF24' },
    { name: 'Advanced fault',  value: 14, color: '#3B82F6' },
    { name: 'Proactive job',   value: 16, color: '#10B981' },
    { name: 'No fault',        value: 60, color: '#6B7280' },
  ]

  // Données failure
  const failureData = [
    { name: 'Action required', value: 46, color: '#EF4444' },
    { name: 'Early fault',     value: 57, color: '#FBBF24' },
    { name: 'Advanced fault',  value: 67, color: '#3B82F6' },
    { name: 'Proactive job',   value: 20, color: '#10B981' },
  ]

  return (
    <div className="space-y-6">
      {/* Tabs factories */}
      <div className="flex space-x-4">
        {['Belgium', 'Russia', 'Spain', 'Italy', 'Germany'].map((f) => (
          <button
            key={f}
            className="px-4 py-2 bg-white rounded-full shadow text-gray-800"
          >
            {f} Factory
          </button>
        ))}
      </div>

      {/* Summary */}
      <Card>
        <div className="grid grid-cols-5 gap-4">
          {summaryItems.map((item, idx) => (
            <div
              key={idx}
              className="p-4 rounded"
              style={{ backgroundColor: item.color }}
            >
              <div className="text-sm text-white">{item.label}</div>
              <div className="text-2xl font-bold text-white">{item.value}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* Charts */}
      <div className="grid grid-cols-2 gap-6">
        {/* Assets status distribution */}
        <Card title="Assets status distribution">
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={statusData}
                dataKey="value"
                nameKey="name"
                innerRadius={40}
                outerRadius={80}
                paddingAngle={5}
              >
                {statusData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          {/* Légende chiffrée */}
          <div className="mt-4 grid grid-cols-2 gap-2">
            {statusData.map((item, i) => (
              <div key={i} className="flex items-center">
                <span
                  className="inline-block w-4 h-4 mr-2"
                  style={{ backgroundColor: item.color }}
                />
                <span className="flex-1 text-sm">{item.name}</span>
                <span className="text-sm font-medium">{item.value + '%'}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Failure mode detected */}
        <Card title="Failure mode detected">
          <ResponsiveContainer width="100%" height={250}>
            <RadialBarChart
              innerRadius="10%"
              outerRadius="80%"
              data={failureData}
              startAngle={90}
              endAngle={-270}
            >
              <RadialBar dataKey="value">
                {failureData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </RadialBar>
              <Tooltip />
            </RadialBarChart>
          </ResponsiveContainer>
          {/* Légende chiffrée */}
          <div className="mt-4 grid grid-cols-2 gap-2">
            {failureData.map((item, i) => (
              <div key={i} className="flex items-center">
                <span
                  className="inline-block w-4 h-4 mr-2"
                  style={{ backgroundColor: item.color }}
                />
                <span className="flex-1 text-sm">{item.name}</span>
                <span className="text-sm font-medium">{item.value + '%'}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* AI Assistance */}
      <Card title="AI Assistance">
        <p>Any suggestion?</p>
        <ol className="list-decimal list-inside space-y-1">
          <li>Analyse undetected failures.</li>
          <li>Implement new PdM technologies.</li>
        </ol>
        <button className="mt-4 px-4 py-2 bg-primary text-white rounded">
          TRY ME!
        </button>
      </Card>
    </div>
  )
}

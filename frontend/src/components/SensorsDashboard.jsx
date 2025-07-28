// SensorsDashboard.jsx
import React, { useState, useMemo } from 'react'
import { columnDefs } from './columns' 
import SummaryCard from './SummaryCard'
import AccordionGroup from './AccordionGroup'

export default function SensorsDashboard({ rawData}) {
  const [showDetails, setShowDetails] = useState(false)

  // Regroupe les données par _company
  const grouped = useMemo(() => {
    return rawData.reduce((acc, d) => {
      const comp = d._company || 'inconnue'
      acc[comp] = acc[comp] || []
      acc[comp].push(d)
      return acc
    }, {})
  }, [rawData])

  return (
    <div>
      {/* Bloc 4 : Cartes de synthèse */}
      <div className="flex flex-wrap">
        {Object.entries(grouped).map(([comp, rows]) => (
          <SummaryCard key={comp} company={comp} rows={rows} />
        ))}
      </div>

      {/* Bloc 4 : Bouton lazy-load */}
      <button
        className="my-4 px-4 py-2 bg-blue-00 text-white rounded"
        onClick={() => setShowDetails(prev => !prev)}
      >
        {showDetails ? "Masquer détails" : "Voir détails"}
      </button>

      {/* Bloc 2 : Accordéons */}
      {showDetails && (
        <AccordionGroup columnDefs={columnDefs} groupedData={grouped} />
      )}
    </div>
  )
}

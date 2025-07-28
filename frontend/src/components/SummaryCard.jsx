// SummaryCard.jsx
import React from 'react'
import { Card, CardHeader, CardTitle, CardContent } from "./ui/card"

export default function SummaryCard({ company, rows }) {
  const count   = rows.length
  const avgBatt = count > 0
    ? Math.round(rows.reduce((sum, r) => sum + r.batt, 0) / count)
    : 0

  return (
    <Card className="w-48 m-2">
      <CardHeader>
        <CardTitle>{company}</CardTitle>
      </CardHeader>
      <CardContent>
        <p>{count} capteur(s)</p>
        <p>Moyenne batt : {avgBatt}</p>
      </CardContent>
    </Card>
  )
}

// AccordionGroup.jsx
import React from 'react'
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent
} from "./ui/accordion"
import DataTable from './DataTable'

export default function AccordionGroup({ columnDefs, groupedData }) {
  return (
    <Accordion type="multiple" defaultValue={Object.keys(groupedData)}>
      {Object.entries(groupedData).map(([company, rows]) => (
        <AccordionItem key={company} value={company}>
          <AccordionTrigger>
            {company} ({rows.length})
          </AccordionTrigger>
          <AccordionContent>
            <DataTable columnDefs={columnDefs} data={rows} />
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  )
}

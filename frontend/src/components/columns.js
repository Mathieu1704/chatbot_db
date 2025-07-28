// columns.js
import React from 'react'
import Sparkline from 'react-sparkline'

export const columnDefs = [
  { accessorKey: 'address', header: 'Address' },
  {
    accessorKey: 'batt',
    header: 'Batt',
    cell: info => {
      const value = info.getValue()
      return (
        <div className="flex items-center">
          <span className="w-10 text-right">{value}</span>
          <div className="ml-2 w-20">
            <Sparkline data={[value]} width={80} height={20} />
          </div>
        </div>
      )
    }
  },
  { accessorKey: '_company', header: 'Client' },
]

import React, { useState, useMemo, useRef, useEffect, use } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getGroupedRowModel,
  getExpandedRowModel,
  flexRender,
  getFilteredRowModel
} from '@tanstack/react-table'
import { Sparklines, SparklinesLine } from 'react-sparklines'
import { MagnifyingGlassIcon, FunnelIcon, AdjustmentsHorizontalIcon } from '@heroicons/react/24/solid'
import { loadTable } from '@/store/tableStore'

/**
 * Tableau virtualisé capable d'afficher des dizaines de milliers de lignes :
 * – si `data` est fourni -> rendu immédiat ;
 * – sinon, on hydrate à la volée depuis IndexedDB via `dataKey`.
 */
export default function DataTable({ columns, data, dataKey, onAssetClick }) {
  // ----------------------
  // Chargement paresseux
  // ----------------------
  const [rows, setRows] = useState(data)
  useEffect(() => {
    if (!rows && dataKey) {
      loadTable(dataKey).then(setRows)
    }
  }, [rows, dataKey])

  //  Détermine automatiquement sur quelle colonne grouper
  const groupingField = columns.includes('transmitter')
    ? 'transmitter'
    : columns.includes('_company')
      ? '_company'
      : columns.includes('company')
        ? 'company'
        : null;


  // Placeholder tant que les données arrivent
  if (!rows) {
    return (
      <div className="p-2 italic text-gray-500">Chargement…</div>
    )
  }

  // Réordonner `columns` pour avoir `asset` en premier
  const orderedColumns = useMemo(() => {
    const misconfOrder = [
      '_company',
      'asset_id',
      'err_name',
      'severity',
      'cause',
      'last_acq',
      'freq_err',
      'errcodes'
    ];
    const isMisconfig = misconfOrder.slice(1).every(c => columns.includes(c));
    if (isMisconfig) {
      if(groupingField) {
        return [
          groupingField, ...misconfOrder
        ]
      }
      return misconfOrder;
    }

    // Sinon, conserve le comportement existant : asset en premier si présent
    if (columns.includes('asset')) {
      const rest = columns.filter(c => c !== 'asset');
      return ['asset', ...rest];
    }
    return columns;
  }, [columns, groupingField]);


  // ----------------------------------------------
  //  State: sorting, grouping, expanded rows
  // ----------------------------------------------
  const [sorting, setSorting] = useState([])
  
  const [grouping, setGrouping] = useState(
    groupingField ? [groupingField] : []
  )
  const hasGrouping = Boolean(groupingField) 


  const [expanded, setExpanded] = useState({})
  const [globalFilter, setGlobalFilter] = useState('')
  const [columnFilters, setColumnFilters] = useState([])
  const [openFilters, setOpenFilters] = useState({})  
  const isFirstRun = useRef(true)




  const toggleColumnFilter = (columnId) => {
    setOpenFilters(prev => ({
      ...prev,
      [columnId]: !prev[columnId],
    }))
  }

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (!e.target.closest('[data-filter-popup]')) {
        setOpenFilters({})
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])


  // ----------------------------------------------
  //  CSV download (Excel‑friendly)
  // ----------------------------------------------
  const downloadCSV = () => {
    if (!rows?.length) return

    const visibleCols = table.getVisibleLeafColumns().map(col => col.id)
    const header = visibleCols.join(',')
    const body = rows.map(r =>
      visibleCols
        .map(c => {
          const raw = r[c] ?? ''
          const str = String(raw).replace(/"/g, '""')
          return `"${str}"`
        })
        .join(',')
    )
    const csv = ['sep=,', header, ...body].join('\r\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `export_${Date.now()}.csv`
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  // ----------------------------------------------
  //  Column definitions
  // ----------------------------------------------
  const columnDefs = useMemo(
    () =>
      orderedColumns.map(key => {
        if (key === 'totalMP') {
          return {accessorKey: 'totalMP', header: 'Total MP'}
        }

        // Si on a un champ transmitter, on l’affiche tel quel
        if (key === 'transmitter') {
          return { accessorKey: 'transmitter', header: 'Transmitter' }
        }
        // Si vous voulez plutôt le nom humain du capteur
        if (key === 'transmitterName') {
          return { accessorKey: 'transmitterName', header: 'Capteur' }
        }

        // Colonne “asset” cliquable
        if (key === 'asset' || key === 'asset_id') {
          return {
            accessorKey: key,
            header: 'Asset',
            cell: info => {
              const assetId = info.getValue();
              const row     = info.row.original;
              // priorise _company (multi-DB), sinon company (mono-DB)
              const clientId = row._company ?? row.company;
              return (
                <button
                  onClick={() => onAssetClick(clientId, assetId)}
                  className="text-purple-600 hover:underline text-sm"
                >
                  {assetId}
                </button>
              );
            }
          };
        }
        if (key === '_company') return { accessorKey: '_company', header: 'Client' }
        if (key === 'address') return { accessorKey: 'address', header: 'Address' }
        if (key === 'batt' || key === 'battery') {
          return {
            accessorKey: key,
            header: 'Battery',
            cell: info => {
              const value = info.getValue()
              return (
                <div className="flex items-center">
                  <span className="w-10 text-right">{value}</span>
                  <div className="ml-2 w-20">
                    <Sparklines data={[value]} width={80} height={20}>
                      <SparklinesLine />
                    </Sparklines>
                  </div>
                </div>
              )
            },
          }
        }
        return { accessorKey: key, header: key }
      }),
    [columns, onAssetClick]
  )

  const defaultColumn = useMemo(
    () => ({
      filterFn: 'includesString',
    }),
    []
  )

  // ----------------------------------------------
  //  React‑Table setup
  // ----------------------------------------------
  const table = useReactTable({
    data: rows,
    columns: columnDefs,
    defaultColumn,
    state: { sorting, grouping, expanded, globalFilter, columnFilters },
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    getFilteredRowModel: getFilteredRowModel(),
    onSortingChange: setSorting,
    onGroupingChange: setGrouping,
    onExpandedChange: setExpanded,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getGroupedRowModel: getGroupedRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    autoResetExpanded: false,
  })
  
  // === AJOUT : auto-dépliage des groupes APRÈS filtrage ===
useEffect(() => {

  if (!globalFilter && columnFilters.length === 0) return

  const newExpanded = {}
  const build = (rows) => {
    rows.forEach(row => {
      if (row.getCanExpand()) {
        newExpanded[row.id] = true
        build(row.subRows)
      }
    })
  }
  build(table.getGroupedRowModel().rows)
  setExpanded(newExpanded)
}, [
  columnFilters,   // ← on réagit à chaque modification des filtres par colonne
  globalFilter,    // ← si vous voulez aussi tenir compte du filtre global
])



  // ----------------------------------------------
  //  Virtualisation (TanStack Virtual)
  // ----------------------------------------------
  const parentRef = useRef(null)
  const rowVirtualizer = useVirtualizer({
    count: table.getRowModel().rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 50,
  })
  const virtualRows = rowVirtualizer.getVirtualItems()
  const paddingTop = virtualRows.length ? virtualRows[0].start : 0
  const paddingBottom = virtualRows.length
    ? rowVirtualizer.getTotalSize() - virtualRows[virtualRows.length - 1].end
    : 0

  // ----------------------------------------------
  //  Render
  // ----------------------------------------------
  return (
    <>
      {/* toolbar */}
      <div className="flex justify-end mb-2 gap-2">
        <button
          onClick={downloadCSV}
          className="px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700"
        >
          Télécharger CSV
        </button>
      </div>

      {/* **Global filter** */}
      <div className="mb-4">
        <div className="flex items-center border border-gray-300 rounded-lg overflow-hidden">
          <MagnifyingGlassIcon className="w-5 h-5 text-gray-400 ml-2"/>
          <input
            value={globalFilter}
            onChange={e => setGlobalFilter(e.target.value)}
            placeholder="Rechercher…"
            className="flex-1 px-3 py-2 text-sm placeholder-gray-500 focus:outline-none bg-white"
          />
        </div>
      </div>

      {/* data table */}
      <div ref={parentRef} className="h-96 overflow-y-auto">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-blue-200 border-b-2 border-black text-black">
            {table.getHeaderGroups().map(headerGroup => (
              <React.Fragment key={headerGroup.id}>
                {/* Ligne des en-têtes avec tri */}
                <tr>
                  {headerGroup.headers.map(header => {
                    const isSorted = header.column.getIsSorted()
                    const isFiltered = !!header.column.getFilterValue()
                    return (
                      <th
                        key={header.id}
                        className="px-6 py-2 text-left select-none"
                      >
                        <div className="flex items-center justify-between cursor-pointer"
                            onClick={header.column.getToggleSortingHandler()}>
                          {/* 1) Titre + tri */}
                          <span className="text-gray-800 font-medium uppercase text-sm">
                            {flexRender(header.column.columnDef.header, header.getContext())}
                          </span>
                          <span className="flex items-center space-x-1">
                            {isSorted === 'asc' && <svg className="w-3 h-3">…▲</svg>}
                            {isSorted === 'desc' && <svg className="w-3 h-3">…▼</svg>}

                            {/* 2) Bouton filtre */}
                            {header.column.getCanFilter() && (
                              <button
                                onClick={e => {
                                  e.stopPropagation()

                                  if (isFiltered) {
                                    // ① un filtre existe déjà → on l’efface immédiatement
                                    header.column.setFilterValue(undefined)
                                    // on referme aussi la pop-up si elle est ouverte
                                    setOpenFilters(prev => ({ ...prev, [header.column.id]: false }))
                                  } else {
                                    // ② aucun filtre actif → on ouvre le pop-up comme avant
                                    toggleColumnFilter(header.column.id)
                                  }
                                }}
                                className="p-1 hover:bg-gray-200 rounded"
                              >
                                <FunnelIcon
                                  className={`w-4 h-4 transition-colors ${
                                    isFiltered ? 'text-indigo-600' : 'text-gray-500'
                                  }`}
                                />
                              </button>
                            )}
                          </span>
                        </div>

                        {/* 3) Pop-up de filtre positionné absolu */}
                        {openFilters[header.column.id] && (
                          <div
                            data-filter-popup
                            className="absolute mt-1 rounded-lg border border-gray-200 shadow-xl bg-white/90 backdrop-blur-sm p-3 z-10"
                            style={{ minWidth: 220 }}
                          >

                            <input
                              type="text"
                              value={header.column.getFilterValue() ?? ''}
                              onChange={e => header.column.setFilterValue(e.target.value)}
                              onKeyDown={e => {
                                if (e.key === 'Enter') toggleColumnFilter(header.column.id)   // ↵ ferme la pop-up
                              }}
                              placeholder="Filtrer…"
                              className="w-full text-sm font-normal border border-gray-300 rounded-md px-3 py-1.5 focus:ring-2 focus:ring-indigo-500 focus:outline-none placeholder-gray-400"
                            />
                            <button
                              onClick={() => {
                                header.column.setFilterValue(undefined)
                                toggleColumnFilter(header.column.id)
                              }}
                              className="text-xs text-blue-600 hover:underline"
                            >
                              Effacer
                            </button>
                          </div>
                        )}
                      </th>
                    )
                  })}
                </tr>

                {/* Ligne des filtres par colonne */}
                {/* <tr>
                  {headerGroup.headers.map(header => (
                    <th key={header.id} className="px-2 py-1">
                      {header.column.getCanFilter() ? (
                        <div className="flex items-center bg-gray-100 border border-gray-200 rounded px-2 py-1">
                          <MagnifyingGlassIcon className="w-4 h-4 text-gray-400 mr-2"/>
                          <input
                            type="text"
                            value={header.column.getFilterValue() ?? ''}
                            onChange={e => header.column.setFilterValue(e.target.value)}
                            placeholder="Filtrer…"
                            className="w-full text-xs placeholder-gray-500 bg-transparent focus:outline-none"
                          />
                        </div>
                      ) : null}
                    </th>
                  ))}
                </tr> */}
              </React.Fragment>
            ))}
          </thead>


          <tbody>
            {paddingTop > 0 && (
              <tr style={{ height: paddingTop }}>
                <td />
              </tr>
            )}

            {virtualRows.map(vRow => {
              const row = table.getRowModel().rows[vRow.index]
              const firstCell = row.getVisibleCells()[0]
              const isGroup = hasGrouping && firstCell?.getIsGrouped?.()

              if (isGroup) {
                const leafRows    = row.getLeafRows()
                const faultyCount = leafRows.length
                const totalCount  = leafRows[0].original.totalMP || faultyCount
                const txName      = leafRows[0].original.transmitterName

                return (
                  <tr
                    key={row.id}
                    className="bg-gray-200 border-t border-gray-300 cursor-pointer"
                    onClick={row.getToggleExpandedHandler()}
                  >
                    <td
                      colSpan={row.getVisibleCells().length}
                      className="px-2 py-1 text-left"
                      style={{ paddingLeft: row.depth * 16 }}
                    >
                      <button className="mr-2 text-xs align-middle">
                        {row.getIsExpanded() ? '▾' : '▸'}
                      </button>
                      {firstCell.getValue()} ({faultyCount}/{totalCount}) – {txName}
                    </td>
                  </tr>
                )
              }

              return (
                <tr key={row.id} className="even:bg-gray-50 hover:bg-gray-300">
                  {row.getVisibleCells().map(cell => {
                    if (cell.getIsPlaceholder()) return <td key={cell.id} />
                    const content = cell.getIsAggregated()
                      ? flexRender(cell.column.columnDef.aggregatedCell, cell.getContext())
                      : flexRender(cell.column.columnDef.cell, cell.getContext())
                    return (
                      <td key={cell.id} className="border px-2 py-1 text-left">
                        {content}
                      </td>
                    )
                  })}
                </tr>
              )
            })}

            {paddingBottom > 0 && (
              <tr style={{ height: paddingBottom }}>
                <td />
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  )
}

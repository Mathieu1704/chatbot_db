import React, { useState, useMemo, useEffect, useCallback } from 'react'
import { AgGridReact } from 'ag-grid-react'
import { ModuleRegistry } from 'ag-grid-community'
import { AllCommunityModule } from 'ag-grid-community'
import { Sparklines, SparklinesLine } from 'react-sparklines'
import { MagnifyingGlassIcon } from '@heroicons/react/24/solid'
import { loadTable } from '@/store/tableStore'

// Enregistrer tous les modules AG Grid Community
ModuleRegistry.registerModules([AllCommunityModule])

/**
 * Cell Renderer pour les boutons Asset
 */
const AssetCellRenderer = ({ value, data, onAssetClick }) => {
  const handleClick = () => {
    if (onAssetClick && data) {
      onAssetClick(data._company, value)
    }
  }

  return (
    <button
      onClick={handleClick}
      className="text-purple-600 hover:underline text-sm"
    >
      {value}
    </button>
  )
}

/**
 * Cell Renderer pour les batteries avec sparkline
 */
const BatteryCellRenderer = ({ value }) => {
  if (value === null || value === undefined) {
    return <span>-</span>
  }

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
}

/**
 * Tableau AG Grid capable d'afficher des dizaines de milliers de lignes :
 * – si `data` est fourni -> rendu immédiat ;
 * – sinon, on hydrate à la volée depuis IndexedDB via `dataKey`.
 */
export default function DataTable({ columns, data, dataKey, onAssetClick }) {
  // ----------------------
  // Chargement paresseux
  // ----------------------
  const [rows, setRows] = useState(data)
  const [quickFilterText, setQuickFilterText] = useState('')
  const [gridApi, setGridApi] = useState(null)

  useEffect(() => {
    if (!rows && dataKey) {
      loadTable(dataKey).then(setRows)
    }
  }, [rows, dataKey])

  // Placeholder tant que les données arrivent
  if (!rows) {
    return (
      <div className="p-2 italic text-gray-500">Chargement…</div>
    )
  }

  // Réordonner `columns` pour avoir `asset` en premier
  const orderedColumns = useMemo(() => {
    if (columns.includes('asset')) {
      const rest = columns.filter(c => c !== 'asset')
      return ['asset', ...rest]
    }
    return columns
  }, [columns])

  // ----------------------
  // Configuration des colonnes AG Grid
  // ----------------------
  const columnDefs = useMemo(() => {
    return orderedColumns.map(key => {
      // Colonne "asset" cliquable
      if (key === 'asset') {
        return {
          field: 'asset',
          headerName: 'Asset',
          cellRenderer: AssetCellRenderer,
          cellRendererParams: { onAssetClick },
          sortable: true,
          filter: true,
          resizable: true,
          minWidth: 100
        }
      }
      
      // Colonne "_company" pour le regroupement
      if (key === '_company') {
        return {
          field: '_company',
          headerName: 'Client',
          rowGroup: true,
          hide: true, // Cachée car elle sera affichée dans la colonne de groupe
          sortable: true,
          filter: true,
          resizable: true
        }
      }
      
      // Colonne "address"
      if (key === 'address') {
        return {
          field: 'address',
          headerName: 'Address',
          sortable: true,
          filter: true,
          resizable: true,
          minWidth: 150,
          flex: 0 // Empêche l'étirement automatique
        }
      }
      
      // Colonnes battery avec sparkline
      if (key === 'batt' || key === 'battery') {
        return {
          field: key,
          headerName: 'Battery',
          cellRenderer: BatteryCellRenderer,
          sortable: true,
          filter: 'agNumberColumnFilter',
          resizable: true,
          minWidth: 140,
          flex: 0 // Empêche l'étirement automatique
        }
      }
      
      // Colonnes par défaut
      return {
        field: key,
        headerName: key,
        sortable: true,
        filter: true,
        resizable: true,
        minWidth: 100,
        flex: 0 // Empêche l'étirement automatique
      }
    })
  }, [orderedColumns, onAssetClick])

  // ----------------------
  // Configuration par défaut des colonnes
  // ----------------------
  const defaultColDef = useMemo(() => ({
    sortable: true,
    filter: true,
    resizable: true,
    enableCellTextSelection: true,
    suppressMenu: false,
    wrapText: true,
    autoHeight: true,
    autoHeaderHeight: true
  }), [])

  // ----------------------
  // Configuration de la colonne de groupe automatique
  // ----------------------
  const autoGroupColumnDef = useMemo(() => ({
    headerName: 'Client',
    field: 'ag-Grid-AutoColumn',
    minWidth: 200,
    resizable: true,
    sortable: true,
    filter: true,
    cellRendererParams: {
      suppressCount: false,
      innerRenderer: (params) => {
        // Afficher le nom du client + nombre d'éléments
        if (params.node.group) {
          return `${params.value} (${params.node.allChildrenCount})`
        }
        return params.value
      }
    }
  }), [])

  // ----------------------
  // Stratégie d'auto-size - Ajuster au contenu sans troncature
  // ----------------------
  const autoSizeStrategy = useMemo(() => ({
    type: 'fitCellContents',
    defaultMinWidth: 100,
    defaultMaxWidth: 300
  }), [])

  // ----------------------
  // Callbacks AG Grid
  // ----------------------
  const onGridReady = useCallback((params) => {
      setGridApi(params.api)
    }, [])

  const onFirstDataRendered = useCallback((params) => {
    // Récupère tous les IDs de colonnes
    const allColumnIds = params.columnApi
      .getAllColumns()
      .map(col => col.getColId())

    // Redimensionne au contenu (cells + header)
    params.columnApi.autoSizeColumns(allColumnIds, /* skipHeader = */ false)
  }, [])


  // ----------------------
  // Export CSV
  // ----------------------
  const downloadCSV = useCallback(() => {
    if (gridApi) {
      gridApi.exportDataAsCsv({
        fileName: `export_${Date.now()}.csv`,
        processCellCallback: (params) => {
          // Traitement spécial pour les cellules avec renderers personnalisés
          if (params.column.getColId() === 'asset') {
            return params.value
          }
          if (params.column.getColId() === 'batt' || params.column.getColId() === 'battery') {
            return params.value
          }
          return params.value
        }
      })
    }
  }, [gridApi])

  // ----------------------
  // Gestion du quick filter
  // ----------------------
  const handleQuickFilterChange = useCallback((e) => {
    setQuickFilterText(e.target.value)
  }, [])

  // ----------------------
  // Vérifier si on a des données company pour le regroupement
  // ----------------------
  const hasCompany = columns.includes('_company')

  // ----------------------
  // Render
  // ----------------------
  return (
    <>
      {/* Toolbar */}
      <div className="flex justify-end mb-2 gap-2">
        <button
          onClick={downloadCSV}
          className="px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700"
        >
          Télécharger CSV
        </button>
      </div>

      {/* Recherche rapide globale */}
      <div className="mb-4">
        <div className="flex items-center border border-gray-300 rounded-lg overflow-hidden">
          <MagnifyingGlassIcon className="w-5 h-5 text-gray-400 ml-2" />
          <input
            value={quickFilterText}
            onChange={handleQuickFilterChange}
            placeholder="Rechercher…"
            className="flex-1 px-3 py-2 text-sm placeholder-gray-500 focus:outline-none bg-white"
          />
        </div>
      </div>

      {/* AG Grid avec scroll horizontal si nécessaire */}
      <div className="ag-theme-alpine h-96 w-full overflow-hidden">
        <AgGridReact
          rowData={rows}
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          autoGroupColumnDef={hasCompany ? autoGroupColumnDef : undefined}
          quickFilterText={quickFilterText}
          animateRows={true}
          groupDefaultExpanded={hasCompany ? 1 : undefined}
          enableCellTextSelection={true}
          domLayout="normal"
          autoSizeStrategy={autoSizeStrategy}
          onGridReady={onGridReady}
          onGridSizeChanged={params => {
            const allIds = params.columnApi.getAllColumns().map(col => col.getId());
            params.columnApi.autoSizeColumns(allIds, true);
          }}
          onFirstDataRendered={onFirstDataRendered}
          suppressRowGroupHidesColumns={true}
          groupDisplayType={hasCompany ? 'singleColumn' : undefined}
          rowSelection="multiple"
          suppressCellFocus={false}
          enableRangeSelection={true}
          suppressHorizontalScroll={false}
          alwaysShowHorizontalScroll={false}
          suppressColumnVirtualisation={true}
          components={{
            assetCellRenderer: AssetCellRenderer,
            batteryCellRenderer: BatteryCellRenderer
          }}
        />
      </div>

      <style jsx global>{`
        .ag-theme-alpine {
          --ag-header-background-color: rgb(191 219 254); /* bg-blue-200 */
          --ag-header-foreground-color: rgb(0 0 0); /* text-black */
          --ag-border-color: rgb(0 0 0); /* border-black */
          --ag-header-column-separator-color: rgb(0 0 0);
          --ag-row-hover-color: rgb(209 213 219); /* hover:bg-gray-300 */
          --ag-odd-row-background-color: rgb(249 250 251); /* even:bg-gray-50 */
          --ag-row-border-color: rgb(229 231 235);
        }
        
        .ag-theme-alpine .ag-header {
          border-bottom: 2px solid black;
        }
        
        .ag-theme-alpine .ag-header-cell-text {
          font-weight: 500;
          text-transform: uppercase;
          font-size: 0.875rem;
          color: rgb(55 65 81); /* text-gray-800 */
          white-space: nowrap;
        }
        
        .ag-theme-alpine .ag-row {
          border: 1px solid rgb(229 231 235);
        }
        
        .ag-theme-alpine .ag-cell {
          padding-left: 0.5rem;
          padding-right: 0.5rem;
          padding-top: 0.25rem;
          padding-bottom: 0.25rem;
          text-align: left;
          font-size: 0.875rem;
          white-space: nowrap;
          overflow: visible;
        }
        
        .ag-theme-alpine .ag-group-expanded .ag-group-contracted {
          background-color: rgb(229 231 235); /* bg-gray-200 */
          border-top: 1px solid rgb(209 213 219); /* border-gray-300 */
        }

        /* Supprimer le scroll global indésirable */
        .ag-theme-alpine .ag-root-wrapper {
          overflow: hidden;
        }
        
        .ag-theme-alpine .ag-body-horizontal-scroll {
          overflow-x: auto;
        }

        /* Assurer que les cellules ne sont pas tronquées */
        .ag-theme-alpine .ag-cell-wrapper {
          overflow: visible;
        }
      `}</style>
    </>
  )
}
// src/components/AssetDetailModal.jsx
import React, { useState, useRef, useEffect } from 'react'

export default function AssetDetailModal({
  stackIndex = 0,
  onClose,
  assetId,
  data,
  loading
}) {
  // Position initiale : décalée par rapport au stackIndex
  const offset = stackIndex * 20
  const [pos, setPos] = useState({ x: 100 + offset, y: 100 + offset })
  const dragRef = useRef(null)
  const dragging = useRef(false)
  const origin = useRef({ x: 0, y: 0 })

  // Démarre le drag
  const onMouseDown = e => {
    dragging.current = true
    origin.current = {
      x: e.clientX - pos.x,
      y: e.clientY - pos.y
    }
    e.preventDefault()
  }
  // Termine le drag
  const onMouseUp = () => {
    dragging.current = false
  }
  // Pendant le drag, on met à jour la position
  const onMouseMove = e => {
    if (!dragging.current) return
    setPos({
      x: e.clientX - origin.current.x,
      y: e.clientY - origin.current.y
    })
  }

  useEffect(() => {
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [])

  return (
    <div
      ref={dragRef}
      className="fixed bg-white rounded-lg shadow-xl overflow-hidden"
      style={{
        width: 320,
        maxHeight: '60vh',
        top: pos.y,
        left: pos.x,
        zIndex: 100 + stackIndex,
        display: 'flex',
        flexDirection: 'column',

        /* ** Ajout resize ** */
        resize: 'both',
        minWidth: 200,
        minHeight: 150,
      }}
    >
      {/* En-tête draggable */}
      <div
        className="cursor-move bg-purple-600 text-white px-4 py-2 flex justify-between items-center"
        onMouseDown={onMouseDown}
      >
        <span className="font-semibold">Asset {assetId}</span>
        <button
          onClick={onClose}
          className="text-white text-xl leading-none hover:text-gray-300"
        >
          &times;
        </button>
      </div>

      {/* Contenu */}
      <div className="p-4 flex-1 overflow-y-auto overflow-x-hidden bg-gray-50">
        {loading && (
          <div className="text-center py-8 text-gray-600">Chargement…</div>
        )}

        {!loading && data && (
          <div className="grid grid-cols-1 gap-y-2 text-sm">
          {Object.entries(data).map(([key, value]) => (
            <div key={key} className="break-words">
              <span className="font-medium text-purple-700">{key}:</span>
              {Array.isArray(value) ? (
                // Affiche chaque élément du tableau à la ligne
                <div className="ml-4 mt-1 space-y-1">
                  {value.map((item, idx) => (
                    <div key={idx} className="text-gray-800">
                      {Array.isArray(item)
                        ? item.join(', ')
                        : String(item)}
                    </div>
                  ))}
                </div>
              ) : (
                <span className="ml-2">{String(value)}</span>
              )}
            </div>
          ))}
        </div>
        )}

        {!loading && !data && (
          <div className="text-red-600">Aucune donnée à afficher.</div>
        )}
      </div>
    </div>
  )
}

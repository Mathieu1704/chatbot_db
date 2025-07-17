import React, { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import DataTable from './DataTable'
import { useNavigate } from 'react-router-dom'         
import { useTopologyStore } from '@/store/useTopologyStore'

export default function Chat() {
  /* ---------- État principal ---------- */
  const stored = localStorage.getItem('chatHistory')
  const initialMessages = stored
    ? JSON.parse(stored)
    : [
        {
          from: 'assistant',
          text: "Bonjour ! Comment puis-je vous aider aujourd'hui ?",
          timestamp: Date.now()
        }
      ]

  const [messages, setMessages] = useState(initialMessages)
  const [input, setInput]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [typing, setTyping]     = useState(false)
  const navigate = useNavigate()
  const setTopology = useTopologyStore(s => s.setTopology)

  /* ---------- Refs & state UI ---------- */
  const containerRef           = useRef(null)
  const textareaRef            = useRef(null)
  const shouldAutoScroll       = useRef(true)      // mis à jour dans onScroll
  const [showJump, setShowJump] = useState(false)  // affiche le bouton "▼"

  /* ---------- Persistance + scroll automatique ---------- */
  useEffect(() => {
    // sauvegarde
    localStorage.setItem('chatHistory', JSON.stringify(messages))

    // scroll vers le bas si l'auto-scroll est permis
    const el = containerRef.current
    if (el && shouldAutoScroll.current) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }
  }, [messages])

  /* ---------- Détection manuelle du scroll de l'utilisateur ---------- */
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const onScroll = () => {
      const distance =
        el.scrollHeight - el.scrollTop - el.clientHeight // px depuis le bas
      shouldAutoScroll.current = distance < 120          // seuil de 120 px
      setShowJump(!shouldAutoScroll.current)
    }

    el.addEventListener('scroll', onScroll)
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  /* ---------- Format heure courte ---------- */
  const formatTime = ts => {
    const d = new Date(ts)
    return isNaN(d.getTime())
      ? ''
      : d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  }

  /* ---------- Réinitialisation ---------- */
  const clearConversation = () => {
    const greeting = {
      from: 'assistant',
      text: "Bonjour ! Comment puis-je vous aider aujourd'hui ?",
      timestamp: Date.now()
    }
    setMessages([greeting])
    localStorage.removeItem('chatHistory')
  }

  /* ---------- Envoi de message ---------- */
  const sendMessage = async () => {
    const text = input.trim()
    if (!text) return

    setMessages(ms => [...ms, { from: 'user', text, timestamp: Date.now() }])
    setInput('')
    setLoading(true)
    setTyping(true)

    try {
      const res = await axios.post('/api/chat', { message: text, locale: 'fr' })
      const { answer, documents, columns, type } = res.data

      /* --- Si la réponse contient un graphe de topologie --- */
      if (res.data.graph) {
        // slug normalisé de l’entreprise renvoyée par l’orchestrateur
        const slug = (res.data.company || '').toLowerCase();

        // 1) on stocke le graphe dans Zustand
        setTopology(slug, res.data.graph);

        // 2) on ouvre /topology?company=<slug>
        navigate(`/topology?company=${encodeURIComponent(slug)}`);
      }                    

      setMessages(ms => {
        const newMs = [
          ...ms,
          { from: 'assistant', text: answer, timestamp: Date.now() }
        ]

        /* --- Tableau reçu ? --- */
        if ((documents && documents.length) || type === 'battery_list') {
          const data = documents?.length ? documents : res.data.rows
          const cols =
            columns?.length
              ? columns
              : res.data.columns || Object.keys(data[0])

          newMs.push({
            from: 'table',
            data,
            columns: cols,
            collapsed: false,
            timestamp: Date.now()
          })

          /* Limiter à 5 tableaux -> on enlève les plus anciens */
          let tableCount = 0
          const filtered = []
          for (let i = newMs.length - 1; i >= 0; i--) {
            const m = newMs[i]
            if (m.from === 'table') {
              tableCount++
              if (tableCount > 5) continue
            }
            filtered.unshift(m)
          }
          return filtered
        }

        return newMs
      })
    } catch {
      setMessages(ms => [
        ...ms,
        {
          from: 'assistant',
          text: 'Erreur de communication.',
          timestamp: Date.now()
        }
      ])
    } finally {
      setLoading(false)
      setTyping(false)
    }
  }

  /* ---------- Handlers UI ---------- */
  const handleSubmit = e => {
    e.preventDefault()
    if (!loading) sendMessage()
  }

  const handleKeyDown = e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const handleInput = e => {
    setInput(e.target.value)
    const ta = textareaRef.current
    if (ta) {
      ta.style.height = 'auto'
      ta.style.height = `${ta.scrollHeight}px`
    }
  }

  /* ---------- Toggle tableau ---------- */
  const toggleTable = idx => {
    setMessages(ms =>
      ms.map((m, i) =>
        i === idx ? { ...m, collapsed: !m.collapsed } : m
      )
    )
  }

  /* ---------- Rendu ---------- */
  return (
    <div className="flex flex-col h-full scroll-smooth">
      {/* En-tête */}
      <div className="flex items-center justify-between p-4 bg-animated-gradient text-white">
        <h2 className="text-lg font-semibold">Chat</h2>
        <button
          onClick={clearConversation}
          className="px-3 py-1 bg-purple-600 text-white rounded-lg hover:bg-purple-700 focus:outline-none focus:ring"
        >
          Effacer la conversation
        </button>
      </div>

      {/* Zone scrollable */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto overflow-x-hidden p-4 bg-gray-50"
      >
        {messages.map((msg, i) => {
          if (msg.from === 'table') {
            return (
              <div key={i} className="mt-4 mb-10 animate-fade-in">
                {/* Barre d’info + bouton */}
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-600">
                    Tableau – {msg.data.length} lignes · {msg.columns.length} colonnes
                  </span>
                  <button
                    onClick={() => toggleTable(i)}
                    className="text-xs text-purple-600 hover:underline focus:outline-none"
                  >
                    {msg.collapsed ? 'Afficher le tableau' : 'Fermer le tableau'}
                  </button>
                </div>

                {/* Carte contenant le tableau */}
                {!msg.collapsed && (
                  <div className="rounded-lg border border-gray-200 shadow-sm bg-white p-2 overflow-x-auto">
                    <DataTable columns={msg.columns} data={msg.data} />
                  </div>
                )}
              </div>
            )
          }

          /* Messages texte (user / assistant) */
          return (
            <div
              key={i}
              className={`flex mb-2 ${
                msg.from === 'user'
                  ? 'justify-end animate-slide-right'
                  : 'justify-start animate-slide-left'
              }`}
            >
              <div className="animate-fade-in">
                <div
                  className={`p-3 rounded-lg inline-block max-w-xs sm:max-w-md ${
                    msg.from === 'user'
                      ? 'bg-blue-100 text-gray-800'
                      : 'bg-gray-200 text-gray-900'
                  }`}
                >
                  {msg.text}
                </div>
                <div className="text-[10px] text-gray-500 mt-1 text-right">
                  {formatTime(msg.timestamp)}
                </div>
              </div>
            </div>
          )
        })}

        {typing && (
          <div className="mt-2 text-sm text-gray-600 italic">
            <span className="typing-dot">•</span>
            <span className="typing-dot">•</span>
            <span className="typing-dot">•</span>
          </div>
        )}
      </div>

      {/* Bouton "▼" pour revenir en bas */}
      {showJump && (
        <button
          onClick={() =>
            containerRef.current?.scrollTo({
              top: containerRef.current.scrollHeight,
              behavior: 'smooth'
            })
          }
          className="fixed bottom-24 right-6 bg-purple-600 text-white rounded-full p-2 shadow-lg hover:bg-purple-700 focus:outline-none"
        >
          ▼
        </button>
      )}

      {/* Formulaire d’envoi */}
      <form
        onSubmit={handleSubmit}
        className="border-t p-4 flex items-end space-x-2 bg-white"
      >
        <textarea
          ref={textareaRef}
          className="flex-1 border rounded-lg p-2 resize-none min-h-[3rem] max-h-24 overflow-y-auto textarea-focus"
          placeholder="Tapez votre message…"
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg disabled:opacity-50 ripple button-pulse flex items-center justify-center"
        >
          {loading ? (
            <svg
              className="w-5 h-5 animate-spin text-white"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v8H4z"
              />
            </svg>
          ) : (
            'Envoyer'
          )}
        </button>
      </form>
    </div>
  )
}

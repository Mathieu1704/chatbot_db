import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import Chat from './components/Chat'
import Topology from "./components/Topology";


export default function App() {
  return (
    <Router>
      <div className="flex h-screen">
        <Sidebar />
        <main className="flex-1 p-6 bg-gray-100 overflow-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/topology" element={<Topology />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}
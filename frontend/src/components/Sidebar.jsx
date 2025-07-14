import { NavLink } from 'react-router-dom'
import { FaHome, FaComments } from 'react-icons/fa'

const links = [
  { name: 'Dashboard', to: '/', icon: <FaHome /> },
  { name: 'Chat', to: '/chat', icon: <FaComments /> }
]

export default function Sidebar() {
  return (
    <nav className="w-64 bg-white shadow-md">
      <div className="p-4 text-2xl font-bold text-primary">AI-See</div>
      <ul>
        {links.map(link => (
          <li key={link.to}>
            <NavLink
              to={link.to}
              className={({ isActive }) =>
                `flex items-center p-4 hover:bg-gray-100 ${isActive ? 'bg-secondary/20' : ''}`
              }
            >
              {link.icon}
              <span className="ml-2">{link.name}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
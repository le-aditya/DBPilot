import { Navigate, Route, Routes } from 'react-router-dom'

import { Landing } from './routes/Landing'
import { Login } from './routes/Login'
import { ProjectDetail } from './routes/ProjectDetail'
import { Projects } from './routes/Projects'
import { ProtectedRoute } from './routes/ProtectedRoute'
import { Register } from './routes/Register'
import { Tokens } from './routes/Tokens'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/projects"
        element={
          <ProtectedRoute>
            <Projects />
          </ProtectedRoute>
        }
      />
      <Route
        path="/projects/:projectId"
        element={
          <ProtectedRoute>
            <ProjectDetail />
          </ProtectedRoute>
        }
      />
      <Route path="/tokens" element={<Tokens />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

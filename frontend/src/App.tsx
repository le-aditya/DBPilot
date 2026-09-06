import { Navigate, Route, Routes } from 'react-router-dom'

import { Tokens } from './routes/Tokens'

export default function App() {
  return (
    <Routes>
      <Route path="/tokens" element={<Tokens />} />
      <Route path="*" element={<Navigate to="/tokens" replace />} />
    </Routes>
  )
}

import { Card } from '../components/ui/Card'
import { Search } from 'lucide-react'

export default function ScanInterface() {
  return (
    <div className="mx-auto max-w-5xl py-8">
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Scan Interface</h1>
      </div>
      <Card className="p-6">
        <div className="flex flex-col items-center justify-center py-12 text-center text-slate-500">
          <Search className="mb-4 h-12 w-12 text-slate-300" />
          <p>Scan functionality will go here.</p>
        </div>
      </Card>
    </div>
  )
}

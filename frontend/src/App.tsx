import { useState, useEffect } from 'react'
import { supabase } from './lib/supabase'
import { Auth } from './components/Auth'
import { EnvioDrive, type DriveStatus } from './components/EnvioDrive'
import type { Session } from '@supabase/supabase-js'

interface DocumentoConferencia {
  contrato: string
  documento: string
  resultado: string
  observacao: string
}

interface DocumentoIdentificado {
  nome: string
  tipo: string
  contrato: string | null
  confianca: string
  observacao: string
}

interface Relatorio {
  autor: string
  processo: string
  processado_em: string
  contratos_encontrados: string[]
  total_documentos: number
  total_nao_identificados: number
  alertas: string[]
  pasta_saida: string
  documentos: DocumentoIdentificado[]
  nao_identificados: DocumentoIdentificado[]
  conferencia: DocumentoConferencia[]
  job_id: string
  download_url: string
}

type Etapa = 'upload' | 'processando' | 'resultado'
type Aba = 'envio' | 'conferencia'

function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [etapa, setEtapa] = useState<Etapa>('upload')
  const [autor, setAutor] = useState('')
  const [processo, setProcesso] = useState('')
  const [modalidade, setModalidade] = useState('emprestimo_consignado')
  const [arquivos, setArquivos] = useState<File[]>([])
  const [relatorio, setRelatorio] = useState<Relatorio | null>(null)
  const [erro, setErro] = useState('')
  const [dragAtivo, setDragAtivo] = useState(false)
  const [driveConectado, setDriveConectado] = useState(false)
  const [driveEnviando, setDriveEnviando] = useState(false)
  const [driveUrl, setDriveUrl] = useState('')
  const [aba, setAba] = useState<Aba>('envio')
  const [driveEscritorio, setDriveEscritorio] = useState<DriveStatus | null>(null)

  const authHeaders = (): Record<string, string> => {
    const token = session?.access_token
    return token ? { 'Authorization': `Bearer ${token}` } : {}
  }

  const checkDriveStatus = async () => {
    try {
      const res = await fetch('/api/drive/status', { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setDriveConectado(data.connected)
      }
    } catch {}
  }

  const conectarDrive = async () => {
    try {
      const res = await fetch('/api/drive/auth', { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        window.location.href = data.auth_url
      }
    } catch {}
  }

  const enviarParaDrive = async () => {
    if (!relatorio?.job_id) return
    setDriveEnviando(true)
    try {
      const res = await fetch(`/api/drive/upload/${relatorio.job_id}`, {
        method: 'POST',
        headers: authHeaders(),
      })
      if (res.ok) {
        const data = await res.json()
        setDriveUrl(data.drive_url)
      } else {
        const err = await res.json()
        setErro(err.detail || 'Erro ao enviar pro Drive')
      }
    } catch {
      setErro('Erro ao enviar pro Drive')
    } finally {
      setDriveEnviando(false)
    }
  }

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session)
      setAuthLoading(false)
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session)
    })

    // Checar se voltou do OAuth do Drive
    const params = new URLSearchParams(window.location.search)
    if (params.get('drive') === 'connected') {
      setDriveConectado(true)
      window.history.replaceState({}, '', window.location.pathname)
    }

    return () => subscription.unsubscribe()
  }, [])

  const checkDriveEscritorio = async () => {
    try {
      const res = await fetch('/api/envios/drive/status', { headers: authHeaders() })
      if (res.ok) setDriveEscritorio(await res.json())
    } catch {}
  }

  useEffect(() => {
    if (session) {
      checkDriveStatus()
      checkDriveEscritorio()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.access_token])

  const logout = async () => {
    await supabase.auth.signOut()
    setSession(null)
    setEtapa('upload')
    setRelatorio(null)
  }

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
      </div>
    )
  }

  if (!session) {
    return <Auth onAuth={() => supabase.auth.getSession().then(({ data: { session } }) => setSession(session))} />
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragAtivo(false)
    const files = Array.from(e.dataTransfer.files)
    setArquivos(prev => [...prev, ...files])
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setArquivos(prev => [...prev, ...Array.from(e.target.files!)])
    }
  }

  const removerArquivo = (index: number) => {
    setArquivos(prev => prev.filter((_, i) => i !== index))
  }

  const processar = async () => {
    if (!autor.trim() || !processo.trim()) {
      setErro('Preencha autor e número do processo.')
      return
    }
    if (arquivos.length === 0) {
      setErro('Adicione pelo menos um arquivo.')
      return
    }

    setErro('')
    setEtapa('processando')

    const formData = new FormData()
    arquivos.forEach(arq => formData.append('arquivos', arq))
    formData.append('autor', autor.trim())
    formData.append('processo', processo.trim())
    formData.append('modalidade', modalidade)

    try {
      const token = session?.access_token
      const res = await fetch('/api/processar', {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        body: formData,
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Erro no processamento')
      }

      const data: Relatorio = await res.json()
      setRelatorio(data)
      setEtapa('resultado')
    } catch (e: any) {
      setErro(e.message || 'Erro inesperado')
      setEtapa('upload')
    }
  }

  const novoProcessamento = () => {
    setEtapa('upload')
    setArquivos([])
    setRelatorio(null)
    setAutor('')
    setProcesso('')
    setErro('')
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h1 className="text-lg font-semibold text-gray-900">Subsídios Processuais</h1>
          </div>
          <div className="flex items-center gap-4">
            <StatusDriveEscritorio status={driveEscritorio} />
            <span className="text-sm text-gray-500">{session.user.user_metadata?.nome || session.user.email}</span>
            <button
              onClick={logout}
              className="text-sm text-gray-400 hover:text-red-500 transition-colors"
            >
              Sair
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex gap-1 mb-6 border-b border-gray-200">
          {([
            ['envio', 'Enviar pro Drive'],
            ['conferencia', 'Conferência (organizar por contrato)'],
          ] as [Aba, string][]).map(([id, label]) => (
            <button
              key={id}
              onClick={() => setAba(id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                aba === id ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className={aba === 'envio' ? '' : 'hidden'}>
          <EnvioDrive token={session.access_token} driveStatus={driveEscritorio} />
        </div>

        {aba === 'conferencia' && etapa === 'upload' && (
          <FormUpload
            autor={autor}
            setAutor={setAutor}
            processo={processo}
            setProcesso={setProcesso}
            modalidade={modalidade}
            setModalidade={setModalidade}
            arquivos={arquivos}
            handleDrop={handleDrop}
            handleFileInput={handleFileInput}
            removerArquivo={removerArquivo}
            dragAtivo={dragAtivo}
            setDragAtivo={setDragAtivo}
            processar={processar}
            erro={erro}
          />
        )}

        {aba === 'conferencia' && etapa === 'processando' && <Processando />}

        {aba === 'conferencia' && etapa === 'resultado' && relatorio && (
          <Resultado
            relatorio={relatorio}
            novoProcessamento={novoProcessamento}
            driveConectado={driveConectado}
            driveEnviando={driveEnviando}
            driveUrl={driveUrl}
            enviarParaDrive={enviarParaDrive}
            conectarDrive={conectarDrive}
          />
        )}
      </main>
    </div>
  )
}

function FormUpload({
  autor, setAutor, processo, setProcesso, modalidade, setModalidade,
  arquivos, handleDrop, handleFileInput, removerArquivo,
  dragAtivo, setDragAtivo, processar, erro,
}: {
  autor: string; setAutor: (v: string) => void
  processo: string; setProcesso: (v: string) => void
  modalidade: string; setModalidade: (v: string) => void
  arquivos: File[]; handleDrop: (e: React.DragEvent) => void
  handleFileInput: (e: React.ChangeEvent<HTMLInputElement>) => void
  removerArquivo: (i: number) => void
  dragAtivo: boolean; setDragAtivo: (v: boolean) => void
  processar: () => void; erro: string
}) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Novo processamento</h2>
        <p className="text-gray-500 mt-1">Envie os arquivos de subsídios para organização automática.</p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <h3 className="font-semibold text-gray-900">Dados do processo</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Nome do autor</label>
            <input
              type="text"
              value={autor}
              onChange={e => setAutor(e.target.value)}
              placeholder="Ex: ROSINEIDE OLEGARIO DE ANDRADE"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Número do processo</label>
            <input
              type="text"
              value={processo}
              onChange={e => setProcesso(e.target.value)}
              placeholder="Ex: 0874410-08.2026.8"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Modalidade</label>
          <select
            value={modalidade}
            onChange={e => setModalidade(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
          >
            <option value="emprestimo_consignado">Empréstimo Consignado</option>
            <option value="cartao_consignado">Cartão Consignado</option>
          </select>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <h3 className="font-semibold text-gray-900">Arquivos</h3>
        <div
          onDragOver={e => { e.preventDefault(); setDragAtivo(true) }}
          onDragLeave={() => setDragAtivo(false)}
          onDrop={handleDrop}
          className={`border-2 border-dashed rounded-xl p-10 text-center transition-colors cursor-pointer ${
            dragAtivo ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
          }`}
          onClick={() => document.getElementById('file-input')?.click()}
        >
          <svg className="w-10 h-10 mx-auto text-gray-400 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          <p className="text-gray-600 font-medium">Arraste arquivos aqui ou clique para selecionar</p>
          <p className="text-sm text-gray-400 mt-1">ZIPs, PDFs, imagens</p>
          <input
            id="file-input"
            type="file"
            multiple
            onChange={handleFileInput}
            className="hidden"
            accept=".zip,.pdf,.jpg,.jpeg,.png"
          />
        </div>

        {arquivos.length > 0 && (
          <div className="space-y-2">
            {arquivos.map((arq, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-2 bg-gray-50 rounded-lg">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs font-medium text-gray-400 uppercase">
                    {arq.name.split('.').pop()}
                  </span>
                  <span className="text-sm text-gray-700 truncate">{arq.name}</span>
                  <span className="text-xs text-gray-400">{(arq.size / 1024).toFixed(0)} KB</span>
                </div>
                <button
                  onClick={() => removerArquivo(i)}
                  className="text-gray-400 hover:text-red-500 transition-colors ml-2"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {erro && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
          {erro}
        </div>
      )}

      <button
        onClick={processar}
        disabled={arquivos.length === 0}
        className="w-full bg-blue-600 text-white py-3 px-6 rounded-xl font-semibold hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Processar subsídios
      </button>
    </div>
  )
}

function Processando() {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <div className="w-12 h-12 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mb-6" />
      <h2 className="text-xl font-semibold text-gray-900">Processando...</h2>
      <p className="text-gray-500 mt-2">Descompactando, identificando e organizando os documentos.</p>
    </div>
  )
}

function Resultado({ relatorio, novoProcessamento, driveConectado, driveEnviando, driveUrl, enviarParaDrive, conectarDrive }: {
  relatorio: Relatorio; novoProcessamento: () => void
  driveConectado: boolean; driveEnviando: boolean; driveUrl: string
  enviarParaDrive: () => void; conectarDrive: () => void
}) {
  const localizados = relatorio.conferencia.filter(c => c.resultado === 'Localizado').length
  const naoLocalizados = relatorio.conferencia.filter(c => c.resultado === 'Não localizado').length
  const manuais = relatorio.conferencia.filter(c => c.resultado === 'Conferência manual').length

  const porContrato: Record<string, DocumentoConferencia[]> = {}
  relatorio.conferencia.forEach(c => {
    if (!porContrato[c.contrato]) porContrato[c.contrato] = []
    porContrato[c.contrato].push(c)
  })

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Processamento concluído</h2>
          <p className="text-gray-500 mt-1">{relatorio.autor} · {relatorio.processo}</p>
        </div>
        <div className="flex items-center gap-3">
          {driveUrl ? (
            <a
              href={driveUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-green-600 text-white px-5 py-2.5 rounded-lg font-medium hover:bg-green-700 transition-colors flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Abrir no Drive
            </a>
          ) : driveConectado ? (
            <button
              onClick={enviarParaDrive}
              disabled={driveEnviando}
              className="bg-green-600 text-white px-5 py-2.5 rounded-lg font-medium hover:bg-green-700 transition-colors flex items-center gap-2 disabled:opacity-50"
            >
              {driveEnviando ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M7.71 3.5L1.15 15l4.58 7.5h6.56l-4.58-7.5L14.27 3.5H7.71zm8.56 0l-6.56 11 4.58 7.5h6.56l-4.58-7.5L22.83 3.5h-6.56z" />
                </svg>
              )}
              {driveEnviando ? 'Enviando...' : 'Enviar pro Drive'}
            </button>
          ) : (
            <button
              onClick={conectarDrive}
              className="bg-white border border-gray-300 text-gray-700 px-5 py-2.5 rounded-lg font-medium hover:bg-gray-50 transition-colors flex items-center gap-2"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                <path d="M7.71 3.5L1.15 15l4.58 7.5h6.56l-4.58-7.5L14.27 3.5H7.71zm8.56 0l-6.56 11 4.58 7.5h6.56l-4.58-7.5L22.83 3.5h-6.56z" />
              </svg>
              Conectar Drive
            </button>
          )}
          <a
            href={relatorio.download_url}
            className="bg-blue-600 text-white px-5 py-2.5 rounded-lg font-medium hover:bg-blue-700 transition-colors flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Baixar ZIP
          </a>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <CardResumo label="Contratos" valor={relatorio.contratos_encontrados.length} cor="blue" />
        <CardResumo label="Documentos" valor={relatorio.total_documentos} cor="gray" />
        <CardResumo label="Localizados" valor={localizados} cor="green" />
        <CardResumo label="Pendentes" valor={naoLocalizados + manuais} cor={naoLocalizados > 0 ? "red" : "gray"} />
      </div>

      {relatorio.alertas.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <h3 className="font-semibold text-amber-800 mb-2">Alertas</h3>
          {relatorio.alertas.map((a, i) => (
            <p key={i} className="text-sm text-amber-700">{a}</p>
          ))}
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900">Conferência por contrato</h3>
        </div>
        <div className="divide-y divide-gray-100">
          {Object.entries(porContrato).map(([contrato, docs]) => (
            <div key={contrato} className="px-6 py-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="font-mono text-sm font-semibold text-gray-900">Contrato {contrato}</span>
                {docs.every(d => d.resultado === 'Localizado') ? (
                  <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">Completo</span>
                ) : (
                  <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full font-medium">Pendências</span>
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                {docs.map((doc, i) => (
                  <div key={i} className="flex items-center gap-2">
                    {doc.resultado === 'Localizado' ? (
                      <svg className="w-4 h-4 text-green-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : doc.resultado === 'Conferência manual' ? (
                      <svg className="w-4 h-4 text-amber-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                      </svg>
                    ) : (
                      <svg className="w-4 h-4 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    )}
                    <span className="text-sm text-gray-700">{doc.documento}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900">Todos os documentos ({relatorio.total_documentos})</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left">
                <th className="px-6 py-3 font-medium text-gray-500">Arquivo</th>
                <th className="px-6 py-3 font-medium text-gray-500">Tipo</th>
                <th className="px-6 py-3 font-medium text-gray-500">Contrato</th>
                <th className="px-6 py-3 font-medium text-gray-500">Confiança</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {relatorio.documentos.map((doc, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-6 py-3 text-gray-700 max-w-xs truncate">{doc.nome}</td>
                  <td className="px-6 py-3 text-gray-700">{doc.tipo}</td>
                  <td className="px-6 py-3 font-mono text-gray-600">{doc.contrato || 'Geral'}</td>
                  <td className="px-6 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      doc.confianca === 'alta' ? 'bg-green-100 text-green-700' :
                      doc.confianca === 'media' ? 'bg-amber-100 text-amber-700' :
                      'bg-red-100 text-red-700'
                    }`}>
                      {doc.confianca}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <button
        onClick={novoProcessamento}
        className="w-full bg-white border border-gray-300 text-gray-700 py-3 px-6 rounded-xl font-semibold hover:bg-gray-50 transition-colors"
      >
        Novo processamento
      </button>
    </div>
  )
}

function StatusDriveEscritorio({ status }: { status: DriveStatus | null }) {
  if (!status) return null
  if (!status.configurado) {
    return <span className="text-xs text-amber-700 bg-amber-50 px-2 py-1 rounded-full">Drive do escritório não configurado</span>
  }
  if (status.erro) {
    return <span className="text-xs text-red-700 bg-red-50 px-2 py-1 rounded-full" title={status.erro}>Drive do escritório com erro</span>
  }
  return (
    <span
      className="text-xs text-green-700 bg-green-50 px-2 py-1 rounded-full"
      title={status.faixas.map(f => f.nome).join('\n')}
    >
      {status.teste ? 'Drive de TESTE' : 'Drive do escritório'} ok · {status.faixas.length} {status.teste ? 'faixas' : 'drives'}
    </span>
  )
}

function CardResumo({ label, valor, cor }: { label: string; valor: number; cor: string }) {
  const cores: Record<string, string> = {
    blue: 'bg-blue-50 text-blue-700',
    green: 'bg-green-50 text-green-700',
    red: 'bg-red-50 text-red-700',
    gray: 'bg-gray-50 text-gray-700',
  }
  return (
    <div className={`rounded-xl p-4 ${cores[cor] || cores.gray}`}>
      <p className="text-2xl font-bold">{valor}</p>
      <p className="text-sm opacity-70">{label}</p>
    </div>
  )
}

export default App

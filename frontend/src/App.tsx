import { useState, useCallback } from 'react'

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

function App() {
  const [etapa, setEtapa] = useState<Etapa>('upload')
  const [autor, setAutor] = useState('')
  const [processo, setProcesso] = useState('')
  const [modalidade, setModalidade] = useState('emprestimo_consignado')
  const [arquivos, setArquivos] = useState<File[]>([])
  const [relatorio, setRelatorio] = useState<Relatorio | null>(null)
  const [erro, setErro] = useState('')
  const [dragAtivo, setDragAtivo] = useState(false)

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragAtivo(false)
    const files = Array.from(e.dataTransfer.files)
    setArquivos(prev => [...prev, ...files])
  }, [])

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
      const res = await fetch('/api/processar', {
        method: 'POST',
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
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h1 className="text-lg font-semibold text-gray-900">Subsídios Processuais</h1>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        {etapa === 'upload' && (
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

        {etapa === 'processando' && <Processando />}

        {etapa === 'resultado' && relatorio && (
          <Resultado relatorio={relatorio} novoProcessamento={novoProcessamento} />
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

function Resultado({ relatorio, novoProcessamento }: { relatorio: Relatorio; novoProcessamento: () => void }) {
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
        <a
          href={relatorio.download_url}
          className="bg-blue-600 text-white px-5 py-2.5 rounded-lg font-medium hover:bg-blue-700 transition-colors flex items-center gap-2"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Baixar organizado
        </a>
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
